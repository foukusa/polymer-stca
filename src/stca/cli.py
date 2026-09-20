# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys
import warnings

import numpy as np
import pandas as pd

from .data import fingerprints_from_strings
from .chemistry import MACCS_NAMES, MACCS_SPEC, maccs_from_smiles
from .errors import STCAError
from .model import ScreeningModel, dump_json, PACKAGE_VERSION
from .pretrained import load_pretrained, list_profiles
from .scan import ScanConfig
from .training import STCA
from .units import ec_to_log10_s_cm, EC_UNITS


def _csv(path):
    frame=pd.read_csv(path,keep_default_na=False)
    if frame.empty: raise STCAError("CSV contains no data rows.")
    return frame


def _out(path,overwrite):
    path=Path(path)
    if path.exists() and not overwrite: raise FileExistsError(f"Output exists: {path}. Pass --overwrite explicitly.")
    path.parent.mkdir(parents=True,exist_ok=True)
    return path


def _features(frame,args):
    if args.features:
        cols=[c.strip() for c in args.features.split(',') if c.strip()]
        if not cols or any(c not in frame for c in cols): raise STCAError("Explicit feature columns missing.")
        return frame[cols],{"feature_names_":cols},None
    if args.smiles_column not in frame: raise STCAError(f"SMILES column {args.smiles_column!r} missing.")
    X,audit=maccs_from_smiles(frame[args.smiles_column].tolist())
    return X,{"feature_names_":MACCS_NAMES,"feature_spec":MACCS_SPEC},audit.canonical_smiles.to_numpy()


def _targets(frame,args):
    if args.target not in frame: raise STCAError(f"Target column {args.target!r} missing.")
    try: y=pd.to_numeric(frame[args.target],errors="raise").to_numpy(dtype=float)
    except ValueError as exc: raise STCAError("The target column must be numeric.") from exc
    if args.ec_input_unit:
        y=ec_to_log10_s_cm(y,args.ec_input_unit)
    if not np.isfinite(y).all(): raise STCAError("Target contains missing or nonfinite values.")
    return y


def _common_inputs(p):
    p.add_argument('--input',required=True)
    p.add_argument('--smiles-column',default='SMILES')
    p.add_argument('--features',help='Comma-separated explicit binary columns; overrides SMILES input.')


def _target_options(p):
    p.add_argument('--target',required=True)
    p.add_argument('--ec-input-unit',choices=EC_UNITS,help='Convert EC to stored log10(S/cm); no guessing.')


def make_parser():
    p=argparse.ArgumentParser(prog='stca',description='STCA frozen rule screening and source-only custom training')
    p.add_argument('--version',action='version',version=PACKAGE_VERSION)
    subs=p.add_subparsers(dest='command',required=True)
    subs.add_parser('profiles',help='List archived rule snapshots and exact signatures.')
    show=subs.add_parser('inspect',help='Show model provenance and rule metadata.')
    g=show.add_mutually_exclusive_group(required=True);g.add_argument('--profile');g.add_argument('--model')
    s=subs.add_parser('screen',help='Screen unlabeled candidates; invalid SMILES never become negative-key matches.')
    _common_inputs(s)
    g=s.add_mutually_exclusive_group(required=True);g.add_argument('--profile');g.add_argument('--model')
    s.add_argument('--tier',type=float,default=.2);s.add_argument('--output',required=True)
    s.add_argument('--errors',choices=['raise','report'],default='raise')
    s.add_argument('--overwrite',action='store_true')
    t=subs.add_parser('train',help='Mine and freeze rules using only the supplied source records.')
    _common_inputs(t);_target_options(t)
    t.add_argument('--output-dir',required=True);t.add_argument('--overwrite',action='store_true')
    t.add_argument('--direction',choices=['high','low'],default='high')
    t.add_argument('--target-name',default='property');t.add_argument('--target-unit',required=True)
    t.add_argument('--tiers',nargs='+',type=float,default=[.3,.2,.1])
    t.add_argument('--hierarchy',choices=['direct','ec_reverse'],default='direct')
    t.add_argument('--scan-mode',choices=['value','unique','quantile'],default='value')
    t.add_argument('--scan-step',type=float,default=1.0)
    t.add_argument('--min-subset-size',type=int,default=1)
    t.add_argument('--max-rank',type=int,default=10);t.add_argument('--family-size',type=int,default=8)
    t.add_argument('--mcc-mode',choices=['positive','nonnegative'],default='positive')
    t.add_argument('--split-column',help='Explicit column containing only train/test. No automatic t-SNE reconstruction.')
    t.add_argument('--group-column',help='Additional source/family ID to audit across an explicit split.')
    e=subs.add_parser('evaluate',help='Evaluate a frozen model without reranking its rules.')
    _common_inputs(e);_target_options(e)
    g=e.add_mutually_exclusive_group(required=True);g.add_argument('--model');g.add_argument('--profile')
    e.add_argument('--tier',type=float,default=.2);e.add_argument('--output',required=True)
    e.add_argument('--cutoff-mode',choices=['fixed_train','dataset_relative'],default='fixed_train')
    e.add_argument('--cutoff',type=float);e.add_argument('--group-column')
    e.add_argument('--overwrite',action='store_true')
    return p


def _load(args):
    return load_pretrained(args.profile) if args.profile else ScreeningModel.load(args.model)


def _run_train(args):
    root=Path(args.output_dir)
    if root.exists() and any(root.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Output directory not empty: {root}. Use a new directory or --overwrite.")
    frame=_csv(args.input);X,kw,canonical=_features(frame,args);y=_targets(frame,args)
    groups=canonical
    extra_groups=None
    if args.group_column:
        if args.group_column not in frame: raise STCAError("Group column missing.")
        extra_groups=frame[args.group_column].astype(str).to_numpy()
        if (extra_groups=='').any(): raise STCAError("Group IDs cannot be empty.")
        if groups is None: groups=extra_groups
    train=np.arange(len(frame));test=np.array([],dtype=int)
    if args.split_column:
        if args.split_column not in frame: raise STCAError("Split column missing.")
        split=frame[args.split_column].astype(str).to_numpy()
        if set(split)!={'train','test'}: raise STCAError("Split must contain both train and test, and no other labels.")
        train=np.flatnonzero(split=='train');test=np.flatnonzero(split=='test')
        if groups is None: raise STCAError("Custom-feature split requires --group-column for identity-overlap auditing.")
        for grouping in (groups,extra_groups):
            if grouping is not None and set(grouping[train])&set(grouping[test]):
                raise STCAError("A canonical structure/group spans train and test.")
    if args.ec_input_unit and args.target_unit!='log10(S/cm)':
        raise STCAError("With --ec-input-unit, --target-unit must be exactly 'log10(S/cm)'.")
    trainer=STCA(direction=args.direction,tiers=args.tiers,
                 scan=ScanConfig(mode=args.scan_mode,step=args.scan_step,min_subset_size=args.min_subset_size),
                 max_rank=args.max_rank,family_size=args.family_size,hierarchy=args.hierarchy,
                 target_name=args.target_name,target_unit=args.target_unit,mcc_mode=args.mcc_mode)
    subset=lambda a,idx: a.iloc[idx] if isinstance(a,pd.DataFrame) else a[idx]
    model=trainer.fit(subset(X,train),y[train],groups=groups[train] if groups is not None else None,
                      provenance={"source_filename":Path(args.input).name,
                                  "split_protocol":"user_declared_train_test" if len(test) else "source_only_no_test_set",
                                  "smiles_policy":"as_provided" if canonical is not None else None},**kw)
    root.mkdir(parents=True,exist_ok=True)
    model.save(root/'model.json',overwrite=args.overwrite)
    trainer.export_diagnostics(root,overwrite=args.overwrite)
    membership=pd.DataFrame({'input_row_position':np.arange(len(frame)),
                             'split':np.where(np.isin(np.arange(len(frame)),test),'test','train')})
    membership.to_csv(root/'split_membership.csv',index=False)
    for tier in trainer.tiers:
        model.rules(tier=tier).to_csv(root/f'rules_tier_{tier:g}.csv',index=False)
    results=[]
    if len(test):
        from .errors import NoValidRuleError
        for tier in trainer.tiers:
            try:
                metrics=model.evaluate(subset(X,test),y[test],tier=tier,groups=groups[test])
            except NoValidRuleError as exc:
                metrics={'tier':tier,'status':'abstain_no_valid_source_rule','reason':str(exc)}
            results.append(metrics)
        dump_json(root/'test_metrics.json',results,overwrite=args.overwrite)
    print(f"Saved frozen model to {root/'model.json'}")
    print('Rules, scan diagnostics and membership saved. '+('Held-out metrics saved without refitting.' if len(test) else 'No held-out evaluation was performed.'))


def main(argv=None) -> int:
    args=make_parser().parse_args(argv)
    try:
        if args.command=='profiles': print(list_profiles().to_string(index=False));return 0
        if args.command=='inspect': print(json.dumps(_load(args).artifact,indent=2));return 0
        if args.command=='train': _run_train(args);return 0
        model=_load(args)
        out=_out(args.output,args.overwrite)
        frame=_csv(args.input)
        if args.command=='screen':
            if args.features:
                X,_,_=_features(frame,args); result=model.screen_fingerprints(X,tier=args.tier)
            else:
                if args.smiles_column not in frame: raise STCAError('SMILES column missing.')
                result=model.screen(frame[args.smiles_column].tolist(),tier=args.tier,errors=args.errors)
            # Preserve all original columns, including identifiers, without ambiguous collisions.
            collision=set(frame.columns)&set(result.columns)
            if collision: frame=frame.rename(columns={c:f'input_{c}' for c in collision})
            pd.concat([frame.reset_index(drop=True),result.reset_index(drop=True)],axis=1).to_csv(out,index=False)
            print(f"Saved {len(result)} candidate records to {out}");return 0
        X,_,canonical=_features(frame,args);y=_targets(frame,args)
        groups=canonical
        if groups is None and args.group_column:
            if args.group_column not in frame: raise STCAError('Group column missing.')
            groups=frame[args.group_column].astype(str).to_numpy()
        if args.ec_input_unit and model.artifact['target_unit']!='log10(S/cm)':
            raise STCAError('EC conversion does not match the model stored unit.')
        metrics=model.evaluate(X,y,tier=args.tier,cutoff_mode=args.cutoff_mode,cutoff=args.cutoff,groups=groups)
        dump_json(out,metrics,overwrite=args.overwrite)
        print(json.dumps(metrics,indent=2));return 0
    except (STCAError,FileNotFoundError,FileExistsError,ImportError,KeyError) as exc:
        print(f"stca: {exc}",file=sys.stderr);return 2

if __name__=='__main__': raise SystemExit(main())
