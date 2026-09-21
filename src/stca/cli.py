# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
# See LICENSE for academic-use terms and permission requirements.

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
    p=argparse.ArgumentParser(prog='stca',description='STCA frozen rule screening and explicit-protocol custom training')
    p.add_argument('--version',action='version',version=PACKAGE_VERSION)
    subs=p.add_subparsers(dest='command',required=True)
    profiles=subs.add_parser('profiles',help='List paired frozen rule profiles and exact signatures.')
    profiles.add_argument('--protocol',choices=['paper','source_locked','legacy_snapshot'],default='paper')
    a=subs.add_parser('paper-audit',help='Check archived rule literals against a separately recorded SI reference; not a numerical refit.')
    a.add_argument('--output')
    a.add_argument('--overwrite',action='store_true')
    f=subs.add_parser('import-family',help='Import a complete resolved primary EC family; no score-based row selection.')
    f.add_argument('--input',required=True);f.add_argument('--profile',required=True,choices=['ec-low','ec-high'])
    f.add_argument('--output',required=True);f.add_argument('--overwrite',action='store_true')
    q=subs.add_parser('train-profile',help='Train using the same named protocol as the paired pretrained profile.')
    _common_inputs(q);_target_options(q)
    q.add_argument('--profile',required=True,choices=['tg-high','ec-low','ec-high'])
    q.add_argument('--tg-unit',choices=['degC','K'],default='degC')
    q.add_argument('--protocol',choices=['paper','source_locked','generic'],default='paper')
    q.add_argument('--selection-input',help='Additional labeled selection CSV required by the paper core protocol; NOT an untouched test set.')
    q.add_argument('--acknowledge-selection-labels',action='store_true')
    q.add_argument('--group-column',help='Explicit record/group ID column; default SMILES grouping uses canonical structure.')
    q.add_argument('--output-dir',required=True);q.add_argument('--overwrite',action='store_true')
    v=subs.add_parser('verify-results',help='Freshly retrain from author output ZIPs and audit rules/metrics; no legacy core scripts needed.')
    v.add_argument('--reference-dir',required=True);v.add_argument('--output',required=True)
    show=subs.add_parser('inspect',help='Show model provenance and rule metadata.')
    show.add_argument('--protocol',choices=['paper','source_locked','legacy_snapshot'],default='paper')
    g=show.add_mutually_exclusive_group(required=True);g.add_argument('--profile');g.add_argument('--model')
    s=subs.add_parser('screen',help='Screen unlabeled candidates; invalid SMILES never become negative-key matches.')
    _common_inputs(s)
    g=s.add_mutually_exclusive_group(required=True);g.add_argument('--profile');g.add_argument('--model')
    s.add_argument('--protocol',choices=['paper','source_locked','legacy_snapshot'],default='paper')
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
    e.add_argument('--protocol',choices=['paper','source_locked','legacy_snapshot'],default='paper')
    e.add_argument('--allow-overlap',action='store_true',help='Explicit retrospective reassessment on known training/selection IDs.')
    e.add_argument('--tier',type=float,default=.2);e.add_argument('--output',required=True)
    e.add_argument('--cutoff-mode',choices=['fixed_train','dataset_relative'],default='fixed_train')
    e.add_argument('--cutoff',type=float);e.add_argument('--group-column')
    e.add_argument('--overwrite',action='store_true')
    return p


def _load(args):
    return load_pretrained(args.profile,protocol=args.protocol) if args.profile else ScreeningModel.load(args.model)


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


def _run_train_profile(args):
    from .protocols import SelectionData
    root=Path(args.output_dir)
    if root.exists() and any(root.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Output directory not empty: {root}")
    if args.profile.startswith('ec-') and args.ec_input_unit is None:
        raise STCAError("EC training requires --ec-input-unit. Units are never inferred.")
    if args.profile=='tg-high' and args.ec_input_unit:
        raise STCAError("EC units cannot be supplied for a Tg task.")
    if args.protocol=='paper' and (not args.selection_input or not args.acknowledge_selection_labels):
        raise STCAError("The paper protocol requires --selection-input and --acknowledge-selection-labels. These labels select the representative. For source-only training use --protocol source_locked (paired with the source_locked pretrained model).")
    if args.protocol!='paper' and (args.selection_input or args.acknowledge_selection_labels):
        raise STCAError("Source-only protocols refuse selection labels.")
    frame=_csv(args.input);X,kw,groups=_features(frame,args);y=_targets(frame,args)
    if args.group_column:
        if args.group_column not in frame: raise STCAError('Group column missing.')
        groups=frame[args.group_column].astype(str).to_numpy()
    if args.profile=='tg-high' and args.tg_unit=='K': y=y-273.15
    selection=None
    if args.selection_input:
        other=_csv(args.selection_input);E,ekw,eg=_features(other,args);ey=_targets(other,args)
        if kw!=ekw: raise STCAError('Source and selection feature definitions differ.')
        if args.group_column:
            if args.group_column not in other: raise STCAError('Selection group column missing.')
            eg=other[args.group_column].astype(str).to_numpy()
        if groups is None or eg is None: raise STCAError('Binary source/selection training requires --group-column.')
        if args.profile=='tg-high' and args.tg_unit=='K': ey=ey-273.15
        selection=SelectionData(E,ey,eg,name='explicit_selection_csv')
    trainer=STCA.for_profile(args.profile,protocol=args.protocol)
    model=trainer.fit(X,y,groups=groups,selection_data=selection,
                     acknowledge_selection_labels=args.acknowledge_selection_labels,**kw)
    root.mkdir(parents=True,exist_ok=True)
    model.save(root/'model.json',overwrite=args.overwrite)
    trainer.export_diagnostics(root,overwrite=args.overwrite)
    print(f"Saved {args.profile}, protocol={args.protocol}: {root/'model.json'}")
    print("Selection labels were used; evaluate on a different untouched test set." if selection else
          "Source-only training; no test labels were used.")


def main(argv=None) -> int:
    args=make_parser().parse_args(argv)
    try:
        if args.command=='profiles': print(list_profiles(protocol=args.protocol).to_string(index=False));return 0
        if args.command=='verify-results':
            from .verified import run
            run(args.reference_dir,args.output);return 0
        if args.command=='inspect': print(json.dumps(_load(args).artifact,indent=2));return 0
        if args.command=='train': _run_train(args);return 0
        if args.command=='train-profile': _run_train_profile(args);return 0
        if args.command=='paper-audit':
            from .paper_audit import audit_bundled_rules
            table=audit_bundled_rules()
            print(table[['profile','tier','literal_status','snapshot_bytes_status','reported_pipeline_CA_rounded']].to_string(index=False))
            print("This invocation checks bundled literals only. Release real-data refit evidence is in assets/verified_refit_summary.json. Run verify-results to repeat the refit locally.")
            if args.output: table.to_csv(_out(args.output,args.overwrite),index=False)
            return 0 if table.literal_status.eq('MATCH').all() and table.snapshot_bytes_status.eq('UNCHANGED').all() else 2
        if args.command=='import-family':
            from .protocols import TemplateFamily
            family=TemplateFamily.from_primary_csv(args.input,profile=args.profile)
            family.save(_out(args.output,args.overwrite),overwrite=args.overwrite)
            print(f"Saved complete resolved family: {args.output}; source provenance still requires verification.")
            return 0
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
        if args.group_column:
            if args.group_column not in frame: raise STCAError('Group column missing.')
            groups=frame[args.group_column].astype(str).to_numpy()
        if args.ec_input_unit and model.artifact['target_unit']!='log10(S/cm)':
            raise STCAError('EC conversion does not match the model stored unit.')
        if model.provenance.get('group_identity_kind')=='PID' and not args.group_column:
            raise STCAError('This reference model stores PID identities; evaluation requires --group-column. Screening needs no groups.')
        metrics=model.evaluate(X,y,tier=args.tier,cutoff_mode=args.cutoff_mode,cutoff=args.cutoff,groups=groups,allow_overlap=args.allow_overlap)
        dump_json(out,metrics,overwrite=args.overwrite)
        print(json.dumps(metrics,indent=2));return 0
    except (STCAError,FileNotFoundError,FileExistsError,ImportError,KeyError) as exc:
        print(f"stca: {exc}",file=sys.stderr);return 2

if __name__=='__main__': raise SystemExit(main())
