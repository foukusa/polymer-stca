# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
"""Replay a saved real-data manifest with separately declared selection protocols.

Never loads manuscript metrics into fit. Never replaces newly discovered rules
with pretrained winners. Does not require original core modules. Does not upload.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import traceback
import numpy as np
import pandas as pd
from . import __version__
from .chemistry import MACCS_NAMES, MACCS_SPEC
from .data import load_legacy_pair
from .errors import STCAError,NoValidRuleError
from .metrics import target_cutoff,labels_at,screening_metrics,strict_harmonic
from .model import dump_json,tier_key
from .paper_audit import paper_reference,audit_bundled_rules
from .pretrained import load_pretrained
from .protocols import SelectionData,TemplateFamily
from .scan import ScanConfig
from .training import STCA
from .units import ec_to_log10_s_cm
from .resampling import full_pipeline_resampling

PRIMARY='PRIMARY_all_STCA_and_SD_WRAcc_top8_patterns.csv'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_family(ec_dir, explicit=None):
    if explicit:
        p=Path(explicit).resolve()
        if not p.is_file(): raise STCAError(f'Primary-family CSV not found: {p}')
        return p
    root=Path(ec_dir)
    candidates=[root/PRIMARY,
        root/'reviewer_ready_electrical_outputs_v12'/'reviewer_audit'/'primary_electrical_comparison'/'tables'/PRIMARY,
        root/'reviewer_audit'/'primary_electrical_comparison'/'tables'/PRIMARY]
    existing=sorted(set(p.resolve() for p in candidates if p.is_file()))
    if len(existing)>1 and len({sha(p) for p in existing})>1:
        raise STCAError('Different primary-family files were found. Specify --primary-family explicitly.')
    return existing[0] if existing else None


def load_manifest_data(manifest):
    cfg=manifest.get('config',{}); records=manifest.get('input_files',[])
    if len(records)!=8:
        raise STCAError('Expected the eight fingerprint/property inputs in the saved real-data manifest.')
    expected={(r['property'],r['split'],r['file']):r['sha256'] for r in records}
    if len(expected)!=8: raise STCAError('Duplicate input records in saved manifest.')
    loaded={};audit=[]
    for prop in ('tg','ec'):
        root=Path(cfg[prop+'_dir']);split_data={}
        for split,stem in [('train','normal'),('test','outliers')]:
            fp=root/f'morgen_{stem}_maccs_fingerprint.csv';yp=root/f'morgen_{stem}_{prop}.csv'
            for p in (fp,yp):
                if not p.is_file(): raise STCAError(f'Missing original input: {p}')
                h=sha(p)
                if expected.get((prop,split,p.name))!=h:
                    raise STCAError(f'INPUT_CHANGED since saved run: {p}. No silent version substitution.')
                audit.append({'property':prop,'split':split,'file':str(p),'sha256':h,'status':'HASH_MATCH'})
            header=cfg.get(prop+'_header','none')
            if header not in ('none','present',False,True): raise STCAError('Unknown header policy in manifest.')
            X,raw,ids=load_legacy_pair(fp,yp,layout=cfg[prop+'_layout'],has_header=header in ('present',True))
            unit=cfg[prop+'_unit']
            if prop=='ec': y=ec_to_log10_s_cm(raw,unit=unit)
            elif unit=='degC': y=raw.copy()
            elif unit=='K': y=raw-273.15
            else: raise STCAError('Unknown Tg unit.')
            split_data[split]=(X,y,ids.astype(str))
        if set(split_data['train'][2])&set(split_data['test'][2]):
            raise STCAError('Original source/comparison PID overlap; resolve explicitly.')
        loaded[prop]=split_data
    return loaded,pd.DataFrame(audit)


def model_metrics(model, data, task, protocol, output, combined=None):
    rows=[]; preds=[]
    X,y,ids=data['train'];E,z,eids=data['test']
    scopes=[('source',X,y,ids),('comparison',E,z,eids),
            ('combined',*(combined if combined is not None else (np.vstack([X,E]),np.concatenate([y,z]),np.concatenate([ids,eids]))))]
    for tier in model.tiers:
        try:rule=model.rule_for(tier)
        except NoValidRuleError:
            rows.append({'task':task,'protocol':protocol,'tier':tier,'scope':'all','status':'NO_VALID_SELECTED_RULE'})
            continue
        for mode in ('dataset_relative','fixed_train'):
            train_cutoff=target_cutoff(y,tier,model.artifact['direction'])
            components=[];valid=[]
            for name,a,b,ii in scopes:
                cutoff=target_cutoff(b,tier,model.artifact['direction']) if mode=='dataset_relative' else train_cutoff
                selected=rule.apply(a)
                api=model.screen_fingerprints(a,tier=tier)['selected'].to_numpy(dtype=bool)
                if not np.array_equal(selected,api):raise STCAError('Direct literal mask differs from screening API.')
                lab=labels_at(b,cutoff,model.artifact['direction'])
                m=screening_metrics(lab,selected,mcc_mode=model.artifact['mcc_mode'])
                components.append(m['average_score']);valid.append(m['valid_screen'])
                role=('TRAINING_RESUBSTITUTION' if name=='source' else
                      'COMBINED_NOT_INDEPENDENT' if name=='combined' else
                      'SELECTION_REASSESSMENT' if model.provenance.get('external_labels_used_for_fit')
                      else 'HISTORICAL_SELECTION_INDEPENDENCE_UNCERTIFIED' if protocol=='archived_snapshot'
                      else 'SOURCE_FROZEN_COMPARISON')
                rows.append({'task':task,'protocol':protocol,'tier':tier,'scope':name,'cutoff_mode':mode,
                    'cutoff':cutoff,'unit':model.artifact['target_unit'],'signature':rule.signature,
                    'evaluation_role':role,'status':'EVALUATED',**m})
                if name=='comparison':
                    preds.extend({'task':task,'protocol':protocol,'tier':tier,'cutoff_mode':mode,
                        'record_id':str(pid),'measured':float(val),'cutoff':cutoff,'selected':bool(pr),
                        'label':bool(tr),'signature':rule.signature}
                        for pid,val,pr,tr in zip(ii,b,selected,lab))
            rows.append({'task':task,'protocol':protocol,'tier':tier,'scope':'core_harmonic',
                'cutoff_mode':mode,'recomputed_CA':strict_harmonic(components,valid),
                'status':'EVALUATED' if all(valid) else 'INVALID_CORE_COMPONENT','signature':rule.signature})
    return rows,preds


def run(args):
    run_dir=Path(args.run_dir).resolve()
    path=run_dir/'realdata'/'run_manifest.json'
    if not path.exists():path=run_dir/'run_manifest.json'
    if not path.is_file():raise STCAError('Existing run_manifest.json was not found.')
    m=json.loads(path.read_text(encoding='utf-8-sig'));cfg=m['config']
    out=Path(args.output).resolve() if args.output else run_dir/('protocol_recheck_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if out.exists():raise STCAError('Use a new output directory.')
    out.mkdir(parents=True)
    status={'package':__version__,'python':platform.python_version(),'created_utc':datetime.now(timezone.utc).isoformat(),
        'input_manifest':str(path),'input_manifest_sha256':sha(path),
        'paper_provenance':'VERSION_PROTOCOL_RECONCILIATION_REQUIRED','automatic_certification':False,
        'full_SI_all_property_bootstrap_reproduced':False,'tasks':[],'errors':[]}
    allmetrics=[];preds=[];parity=[];refs={(r['profile'],r['tier']):r for r in paper_reference()['rows']}
    try:
        data,input_audit=load_manifest_data(m);input_audit.to_csv(out/'input_audit.csv',index=False)
        audit_bundled_rules().to_csv(out/'bundled_rule_reference_audit.csv',index=False)
        primary=find_family(cfg['ec_dir'],args.primary_family)
        status['primary_family_file']=str(primary) if primary else None
        status['primary_family_sha256']=sha(primary) if primary else None
        for task in ('tg-high','ec-low','ec-high'):
            prop='tg' if task=='tg-high' else 'ec';ds=data[prop]
            X,y,ids=ds['train'];E,z,eids=ds['test']
            combined=None
            if prop=='ec' and args.ec_all_fingerprint:
                ax, ay, ai=load_legacy_pair(args.ec_all_fingerprint,args.ec_all_property,
                    layout=cfg['ec_layout'],has_header=cfg.get('ec_header','none') in ('present',True))
                combined=(ax,ec_to_log10_s_cm(ay,unit=cfg['ec_unit']),ai.astype(str))
                from collections import Counter
                if Counter(combined[2])!=Counter(np.concatenate([ids,eids])):
                    raise STCAError('Explicit EC-all membership differs from source+comparison.')
                order={k:i for i,k in enumerate(combined[2])}
                orig_ids=np.concatenate([ids,eids]);ind=[order[k] for k in orig_ids]
                status['explicit_ec_all_differences']={
                    'target_difference_count':int(np.sum(~np.isclose(combined[1][ind],np.concatenate([y,z]),rtol=0,atol=1e-12))),
                    'fingerprint_difference_count':int(np.sum(np.any(combined[0][ind]!=np.vstack([X,E]),axis=1)))}
                status['explicit_ec_all']={'fingerprint_sha256':sha(args.ec_all_fingerprint),
                    'property_sha256':sha(args.ec_all_property),'source':'explicit_user_supplied'}
            models=[('archived_snapshot',load_pretrained(task,protocol='legacy_snapshot',warn=False),None)]
            if args.mode!='screen_only':
                scan=ScanConfig(step=float(cfg.get(prop+'_step',1 if prop=='tg' else .01)),
                    min_subset_size=int(cfg.get(prop+'_min_subset',1)),max_points=int(cfg.get('max_scan_points',10000)))
                config=dict(scan=scan,max_rank=int(cfg.get(prop+'_max_rank',10 if prop=='tg' else 35)),family_size=int(cfg.get('family_size',8)))
                experiments=[('source_locked',None)]
                if args.mode=='compare_protocols':
                    if prop=='tg':experiments.append(('thermal_core',None))
                    elif primary is None:
                        status['tasks'].append({'task':task,'protocol':'electrical_primary','status':'REFERENCE_FAMILY_MISSING',
                           'reason':'Full resolved primary-family table required; not inferred from a pretrained winner.'})
                    else:
                        family=TemplateFamily.from_primary_csv(primary,profile=task)
                        experiments.extend([('template_source_locked',family),('electrical_primary',family)])
                for protocol,family in experiments:
                    try:
                        trainer=STCA.for_profile(task,protocol='generic' if protocol=='source_locked' else protocol,template_family=family,**config)
                        # Use the same explicitly logged V13 head(n) construction for both
                        # imported-family comparisons; only their selection scope differs.
                        if family is not None:trainer.template_missing='truncate'
                        kwargs={}
                        if trainer.selection!='source_as':
                            kwargs={'selection_data':SelectionData(E,z,eids),'acknowledge_selection_labels':True}
                            if combined is not None: kwargs['combined_data']=SelectionData(*combined)
                        model=trainer.fit(X,y,feature_names_=MACCS_NAMES,feature_spec=MACCS_SPEC,groups=ids,**kwargs)
                        models.append((protocol,model,trainer))
                        if args.repeats and combined is not None:
                            raise STCAError("Resampling a separate core-all representation needs a joined per-ID resampling plan; it is not silently replaced by union resampling.")
                        if args.repeats:
                            for kind in ('bootstrap','permutation'):
                                raw,summary=full_pipeline_resampling(trainer,(X,y),(E,z),kind=kind,
                                    repeats=args.repeats,seed=args.seed,feature_names=MACCS_NAMES,feature_spec=MACCS_SPEC)
                                raw.to_csv(out/f'{task}_{protocol}_{kind}_replicates.csv',index=False)
                                summary.to_csv(out/f'{task}_{protocol}_{kind}_summary.csv',index=False)
                    except STCAError as exc:
                        status['tasks'].append({'task':task,'protocol':protocol,'status':'FIT_FAILED','error':str(exc)})
            for protocol,model,trainer in models:
                model.save(out/f'{task}_{protocol}.json')
                if trainer:trainer.export_diagnostics(out/'diagnostics'/f'{task}_{protocol}')
                met,pr=model_metrics(model,ds,task,protocol,out,combined=combined);allmetrics+=met;preds+=pr
                status['tasks'].append({'task':task,'protocol':protocol,'status':'EVALUATED',
                    'selection':model.provenance.get('selection_protocol')})
                for tier in model.tiers:
                    ref=refs[(task,tier)]
                    try:sig=model.rule_for(tier).signature
                    except NoValidRuleError:sig=None
                    h=next((r.get('recomputed_CA') for r in met if r.get('tier')==tier and r.get('scope')=='core_harmonic' and r.get('cutoff_mode')=='dataset_relative'),None)
                    present=None;retained=None
                    if trainer:
                        cand=trainer.candidate_table_
                        part=cand[cand.tier.eq(tier)]
                        present=bool(part.signature.eq(ref['reference_signature']).any())
                        retained=bool((part.signature.eq(ref['reference_signature'])&part.in_retained_family).any())
                    parity.append({'task':task,'protocol':protocol,'tier':tier,
                        'reference_signature':ref['reference_signature'],'discovered_signature':sig,
                        'signature_status':'MATCH' if sig==ref['reference_signature'] else 'NO_SELECTED_RULE' if sig is None else 'DIFFERENT',
                        'reference_in_candidates':present,'reference_in_retained_family':retained,
                        'reported_CA_rounded':ref['reported_pipeline_CA_rounded'],'recomputed_CA':h,
                        'rounded_CA_match':abs(h-ref['reported_pipeline_CA_rounded'])<.0005000001 if h is not None else None,
                        'interpretation':'ARCHIVE_APPLICATION_NOT_DISCOVERY' if protocol=='archived_snapshot' else 'PROTOCOL_COMPARISON_NOT_AUTOMATIC_CERTIFICATION'})
        pd.DataFrame(allmetrics).to_csv(out/'metrics.csv',index=False)
        pd.DataFrame(preds).to_csv(out/'comparison_predictions.csv',index=False)
        pd.DataFrame(parity).to_csv(out/'final_rule_parity.csv',index=False)
    except Exception as exc:
        status['errors'].append({'type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()})
    dump_json(out/'status.json',status)
    print(f'Protocol audit written to: {out}')
    for row in status['tasks']:
        print(row['task'],row['protocol'],row['status'])
    if status['errors']:
        print(status['errors'][0]['error']);return 2
    print('No reference scores entered training. A matching rule alone is not a complete provenance certification.')
    return 2 if any(r['status'] in ('FIT_FAILED','REFERENCE_FAMILY_MISSING') for r in status['tasks']) else 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True);p.add_argument('--output');p.add_argument('--primary-family')
    p.add_argument('--ec-all-fingerprint');p.add_argument('--ec-all-property')
    p.add_argument('--mode',choices=['screen_only','source_locked','compare_protocols'],default='compare_protocols')
    p.add_argument('--repeats',type=int,default=0,help='Explicit expensive full-discovery record resampling; 0 disables it.')
    p.add_argument('--seed',type=int,default=20260810)
    args=p.parse_args(argv)
    if bool(args.ec_all_fingerprint)!=bool(args.ec_all_property):p.error('Supply both EC-all files, or neither.')
    if args.repeats<0:p.error('--repeats must be nonnegative.')
    return run(args)

if __name__=='__main__':raise SystemExit(main())
