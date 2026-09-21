# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
"""Real-data refit against the five author-supplied output archives.

Only known text/CSV members are read; archives are never extracted or executed.
Original archived scores enter assertions AFTER fitting, never model selection.
No measurements, SMILES or per-material predictions are included in the wheel.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import sys
import zipfile
import numpy as np
import pandas as pd
import scipy
from .chemistry import MACCS_NAMES, MACCS_SPEC, maccs_from_smiles
from .errors import STCAError
from .legacy import rule_from_signature
from .metrics import target_cutoff, labels_at
from .model import ScreeningModel, dump_json, tier_key, PACKAGE_VERSION
from .pretrained import load_pretrained
from .protocols import SelectionData, bundled_primary_family
from .training import STCA

THERMAL = 'reviewer_ready_thermal_complete_outputs'
ELECTRICAL = 'reviewer_ready_electrical_family_transfer_structure_outputs_v15'
FAMILY = 'family_level_EC_to_epsAC/BOTTOM_and_TOP_EC_picked_family_all_members.csv'
SUPPLEMENTS = ('reviewer_ready_thermal_gap_supplement_outputs',
 'reviewer_ready_electrical_gap_supplement_outputs_v13',
 'reviewer_ready_electrical_family_transfer_structure_outputs_v14')


class ReferenceArchive:
    def __init__(self, directory, name):
        self.name = name
        root = Path(directory)
        self.path = root / (name + '.zip')
        self.folder = root / name
        if not self.path.is_file() and not self.folder.is_dir():
            raise FileNotFoundError(f'Missing {self.path}; an extracted {self.folder} is also accepted.')
    def read(self, relative):
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise STCAError('Unsafe reference member.')
        if self.path.is_file():
            with zipfile.ZipFile(self.path) as archive:
                member = self.name + '/' + path.as_posix()
                info = archive.getinfo(member)
                if info.file_size > 40_000_000:
                    raise STCAError('Reference member exceeds 40 MB limit.')
                return archive.read(member)
        f = self.folder / relative
        if not f.resolve().is_relative_to(self.folder.resolve()):
            raise STCAError('Reference path escapes its folder.')
        return f.read_bytes()
    def csv(self, relative): return pd.read_csv(io.BytesIO(self.read(relative)))
    def json(self, relative): return json.loads(self.read(relative).decode('utf-8-sig'))
    def identity(self):
        return {'archive': self.name, 'zip_sha256': hashlib.sha256(self.path.read_bytes()).hexdigest() if self.path.is_file() else None}


def independent_metrics(y, selected):
    """Independent confusion-count implementation for checking package outputs."""
    y = np.asarray(y, bool); p = np.asarray(selected, bool)
    tp = int(np.count_nonzero(y & p)); fp = int(np.count_nonzero(~y & p))
    fn = int(np.count_nonzero(y & ~p)); tn = int(np.count_nonzero(~y & ~p))
    div = lambda a,b: a/b if b else 0.0
    den = math.sqrt(float((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)))
    precision=div(tp,tp+fp);recall=div(tp,tp+fn);f1=div(2*tp,2*tp+fp+fn)
    mcc=div(tp*tn-fp*fn,den)
    return dict(n=len(y),positive_n=tp+fn,negative_n=tn+fp,selected_n=tp+fp,
        tp=tp,fp=fp,tn=tn,fn=fn,precision=precision,recall=recall,f1=f1,mcc=mcc,
        coverage=div(tp+fp,len(y)),average_score=(precision+f1+mcc)/3,
        specificity=div(tn,tn+fp))


def _structure_table(frame):
    required={'pid','smiles','property'}
    if not required.issubset(frame): raise STCAError('Reference structure/target columns missing.')
    if frame.pid.isna().any() or frame.pid.duplicated().any(): raise STCAError('Reference PIDs must be unique and nonempty.')
    y=pd.to_numeric(frame['property'],errors='raise').to_numpy(float)
    if not np.isfinite(y).all(): raise STCAError('Nonfinite reference targets.')
    X,audit=maccs_from_smiles(frame.smiles.tolist())
    return X,y,frame.pid.astype(str).to_numpy(),audit


def _scope_mask(scope, train):
    if scope.endswith('_inter'): return train
    if scope.endswith('_extra'): return ~train
    if scope.endswith('_all'): return np.ones(len(train),bool)
    raise STCAError('Unknown reference scope: '+scope)


def check_reference_metrics(frame, X, y, train, *, electrical):
    """Validate archived literal responses independently, including scope labels.

    EC uses a documented first-normal_n row-order reconstruction. It is accepted
    only after every family member/scope reproduces the uploaded reference counts
    and metrics. This is not a claim to possess the omitted original split CSV.
    """
    checks=[]
    for _,row in frame.iterrows():
        scopes=('EC_inter','EC_extra','EC_all') if electrical else (row.dataset,)
        direction='high' if not electrical or row.regime=='conduction' else 'low'
        tier=(100-float(row.percentile))/100
        rule=rule_from_signature(row.pattern_signature)
        for scope in scopes:
            mask=_scope_mask(scope,train)
            # Direct NumPy percentile and independent metric formulas.
            q=1-tier if direction=='high' else tier
            cutoff=float(np.quantile(y[mask],q,method='linear'))
            labels=y[mask]>=cutoff if direction=='high' else y[mask]<=cutoff
            m=independent_metrics(labels,rule.apply(X[mask]))
            names={'tp':'TP','fp':'FP','mcc':'MCC','precision':'Precision','f1':'F1',
                   'coverage':'Coverage','average_score':'AS','positive_n':'positive_n','selected_n':'selected_n'}
            fields=names if electrical else {k:k for k in m}
            differences=[];max_error=0.0
            for key,name in fields.items():
                col=f'{scope}_{name}' if electrical else name
                expected=float(row[col]);actual=float(m[key]);err=abs(actual-expected)
                max_error=max(max_error,err)
                integer=key in ('n','positive_n','negative_n','selected_n','tp','fp','tn','fn')
                same=actual==expected if integer else np.isclose(actual,expected,rtol=1e-9,atol=1e-12)
                if not same: differences.append(key)
            if not electrical and not np.isclose(cutoff,float(row.cutoff_raw),rtol=0,atol=1e-10): differences.append('cutoff')
            checks.append({'task':'tg-high' if not electrical else 'ec-high' if direction=='high' else 'ec-low',
                'tier':tier,'scope':scope,'signature':rule.signature,'status':'MATCH' if not differences else 'MISMATCH',
                'different_fields':','.join(differences),'max_abs_error':max_error,**m})
    return pd.DataFrame(checks)


def _fit(profile, protocol, X,y,ids,train):
    trainer=STCA.for_profile(profile,protocol=protocol)
    kw=dict(feature_names_=MACCS_NAMES,feature_spec=MACCS_SPEC,groups=ids[train])
    if protocol=='paper':
        kw.update(selection_data=SelectionData(X[~train],y[~train],ids[~train],name='historical_extra_selection'),
                  acknowledge_selection_labels=True)
    model=trainer.fit(X[train],y[train],**kw)
    return trainer,model


def run(reference_dir, output, *, write_pretrained=None):
    """Freshly compute and audit. Writing bundled assets is maintainer-only.

    Validation predictions may contain user PIDs and must remain private. Only
    derived model JSONs/aggregate reports should be committed to the public repo.
    """
    root=Path(output)
    if root.exists() and any(root.iterdir()): raise FileExistsError('Use a new output directory: '+str(root))
    root.mkdir(parents=True,exist_ok=True)
    ta=ReferenceArchive(reference_dir,THERMAL);ea=ReferenceArchive(reference_dir,ELECTRICAL)
    td=ta.csv('split_membership/submitted_tsne_split_membership_audit.csv')
    if set(td.submitted_split)!= {'inter','extra'}: raise STCAError('Unexpected thermal split labels.')
    tx,ty,ti,tchem=_structure_table(td);ttrain=(td.submitted_split=='inter').to_numpy()
    ed=ea.csv('smiles_ec_all_build/smiles_ec_all_validated_with_header.csv')
    ex,ey,ei,echem=_structure_table(ed)
    build=ea.csv('smiles_ec_all_build/smiles_ec_all_build_audit.csv').iloc[0]
    if len(ex)!=int(build.combined_n) or int(build.normal_n)+int(build.outliers_n)!=len(ex): raise STCAError('EC build counts inconsistent.')
    etrain=np.arange(len(ex))<int(build.normal_n)
    tgref=ta.csv('tables/all_candidate_dataset_metrics.csv')
    tgref=tgref[(tgref.method=='STCA')&tgref.dataset.isin(['Tg_inter','Tg_extra','Tg_all'])]
    ecref=ea.csv(FAMILY);ecref=ecref[ecref.method=='STCA']
    data_checks=pd.concat([check_reference_metrics(tgref,tx,ty,ttrain,electrical=False),
        check_reference_metrics(ecref,ex,ey,etrain,electrical=True)],ignore_index=True)
    data_checks.to_csv(root/'archived_rule_metric_parity.csv',index=False)
    if not data_checks.status.eq('MATCH').all():
        raise STCAError('Input/rule-response parity failed. No fitted assets exported; inspect archived_rule_metric_parity.csv.')
    # This EC split reconstruction is not guessed silently: all 171 member/scope
    # comparisons above must pass BEFORE it is supplied to any fit.
    tgbest=ta.csv('tables/selected_advantageous_patterns_by_harmonic_Tg_core.csv')
    tgbest=tgbest[(tgbest.method=='STCA')&(tgbest.selected_for_final_use==True)]
    tglocked=ta.csv('tables/locked_inter_top1_frozen_external_summary.csv');tglocked=tglocked[tglocked.method=='STCA']
    artifacts={};trainers={};parity=[];predictions=[];family_checks=[];fresh_metrics=[];recipes=[];lower_level=[]
    for profile in ('tg-high','ec-low','ec-high'):
        ec=profile.startswith('ec');X,y,ids,train=(ex,ey,ei,etrain) if ec else (tx,ty,ti,ttrain)
        for protocol in ('paper','source_locked'):
            trainer,model=_fit(profile,protocol,X,y,ids,train)
            trainers[(profile,protocol)]=trainer
            a=model.artifact
            a['provenance'].update({'kind':'verified_refit_'+protocol,'preset_profile':profile,'paired_protocol':protocol,
                'verification_source':'author_uploaded_results_20260921','group_identity_kind':'PID',
                'input_structure_policy':'Use uploaded SMILES as provided; regenerate RDKit MACCS167; no recapping.',
                'split_membership_source':'explicit_thermal_PID_split' if not ec else 'row_order_reconstruction_checked_against_all_171_archived_member_scope_metrics',
                'original_raw_fingerprint_bitwise_recheck':'NOT_AVAILABLE_original_fingerprint_CSVs_not_in_archives',
                'external_labels_used_for_fit':protocol=='paper',
                'prospective_accuracy_certified':False})
            model=ScreeningModel(a)
            artifacts[(profile,protocol)]=model
            model.save(root/'models'/f'{profile}_{protocol}.json')
            trainer.export_diagnostics(root/'diagnostics'/f'{profile}_{protocol}')
            # Recreate trainer solely from recipe, not artifact rule fields.
            recreated=model.new_trainer()
            config_same=(recreated.selection==trainer.selection and recreated.hierarchy==trainer.hierarchy
                         and recreated.scan==trainer.scan and recreated.max_rank==trainer.max_rank)
            replay_kw=dict(feature_names_=MACCS_NAMES,feature_spec=MACCS_SPEC,groups=ids[train])
            if protocol=='paper':
                replay_kw.update(selection_data=SelectionData(X[~train],y[~train],ids[~train]),acknowledge_selection_labels=True)
            replay=recreated.fit(X[train],y[train],**replay_kw)
            replay_equal=all(replay.rule_for(t).signature==model.rule_for(t).signature and
                             np.array_equal(replay.rule_for(t).apply(X),model.rule_for(t).apply(X)) for t in model.tiers)
            recipes.append({'profile':profile,'protocol':protocol,'status':'MATCH' if config_same and replay_equal else 'MISMATCH',
                            'fresh_fit_from_saved_recipe':True,'all_record_masks_equal':replay_equal})
            for tier in model.tiers:
                perc=round(100*(1-tier),8)
                if not ec:
                    ref=(tgbest if protocol=='paper' else tglocked)
                    row=ref[np.isclose(ref.percentile,perc)].iloc[0]
                    expected_sig=row.pattern_signature
                    expected_score=float(row.hm_Tg_core if protocol=='paper' else row.AS_Tg_inter)
                else:
                    sub=ecref[(ecref.regime==('insulation' if profile=='ec-low' else 'conduction'))&np.isclose(ecref.percentile,perc)]
                    col='H_EC_core_same_rule' if protocol=='paper' else 'EC_inter_AS'
                    valid=sub[col].notna() if protocol=='paper' else sub.EC_inter_valid.astype(bool)
                    row=sub[valid].sort_values([col,'family_member_rank'],ascending=[False,True],kind='stable').iloc[0]
                    expected_sig=row.pattern_signature;expected_score=float(row[col])
                rule=model.rule_for(tier);score=model.artifact['tiers'][tier_key(tier)]['selection_score']
                try:
                    bundled=load_pretrained(profile,protocol=protocol,warn=False)
                    bundled_sig=bundled.rule_for(tier).signature
                    packaged=bool(np.array_equal(rule.apply(X),bundled.rule_for(tier).apply(X)))
                except FileNotFoundError:
                    bundled_sig=None;packaged=None
                # Old SI snapshot is an independent frozen rule reference for paper.
                old=load_pretrained(profile,protocol='legacy_snapshot',warn=False) if protocol=='paper' else None
                old_match=bool(np.array_equal(rule.apply(X),old.rule_for(tier).apply(X))) if old else None
                parity.append({'profile':profile,'protocol':protocol,'tier':tier,'signature':rule.signature,
                    'reference_signature':expected_sig,'reference_score':expected_score,'recomputed_score':score,
                    'score_abs_error':abs(score-expected_score),'final_rule_status':'MATCH' if rule.signature==expected_sig else 'MISMATCH',
                    'score_status':'MATCH' if np.isclose(score,expected_score,rtol=1e-9,atol=1e-12) else 'MISMATCH',
                    'old_snapshot_mask_equal':old_match,'bundled_signature':bundled_sig,'bundled_mask_equal':packaged,
                    'all_n':len(X),'extra_n':int((~train).sum())})
                candidate=trainer.candidate_table_[np.isclose(trainer.candidate_table_.tier,tier)]
                if ec:
                    ref_family=sub.pattern_signature.tolist()
                    actual=candidate[candidate.in_retained_family].signature.tolist()
                else:
                    source=ta.csv('tables/selected_advantageous_patterns_by_harmonic_Tg_core.csv')
                    ref_family=source[(source.method=='STCA')&np.isclose(source.percentile,perc)].pattern_signature.tolist()
                    actual=candidate[candidate.in_retained_family].signature.tolist()
                family_checks.append({'profile':profile,'protocol':protocol,'tier':tier,'reference_family_n':len(ref_family),
                    'actual_family_n':len(actual),'status':'MATCH' if sorted(actual)==sorted(ref_family) else 'MISMATCH'})
                for scope,mask in [('inter',train),('extra',~train),('all',np.ones(len(X),bool))]:
                    for mode in ('dataset_relative','fixed_train'):
                        m=model.evaluate(X[mask],y[mask],tier=tier,cutoff_mode=mode,groups=ids[mask],allow_overlap=True)
                        fresh_metrics.append({'profile':profile,'protocol':protocol,'scope':scope,'cutoff_mode':mode,**m})
                    for pid,value,selected in zip(ids[mask],y[mask],rule.apply(X[mask])):
                        predictions.append({'profile':profile,'protocol':protocol,'tier':tier,'scope':scope,
                            'pid':pid,'measured_value':float(value),'selected':bool(selected),'signature':rule.signature})
            if not ec and protocol=='paper':
                fresh=trainer.scan_result_.table.set_index('key')
                ranked=trainer.model_.artifact['signed_rankings']
                for sign in ('positive','negative'):
                    ref=ta.csv(f'tables/STCA_{sign}_ranking_used.csv').set_index('key')
                    shared=ref.index.intersection(fresh.index)
                    for k in shared:
                        old=float(ref.loc[k,'score']);new=float(fresh.loc[k,'correlation'])
                        lower_level.append({'kind':'correlation','sign':sign,'key':int(k),'reference':old,'actual':new,'abs_difference':abs(old-new),
                            'status':'MATCH' if np.isclose(old,new,rtol=1e-9,atol=1e-12) else 'ARCHIVED_PRECOMPUTED_COEFFICIENT_DIFFERENCE'})
                    prefix=ref.sort_values('rank').index[:10].tolist()
                    lower_level.append({'kind':'used_prefix','sign':sign,'status':'MATCH' if prefix==ranked[sign+'_keys'][:10] else 'MISMATCH'})
    comparisons=pd.DataFrame(parity);families=pd.DataFrame(family_checks)
    comparisons.to_csv(root/'final_rule_parity.csv',index=False);families.to_csv(root/'candidate_family_parity.csv',index=False)
    pd.DataFrame(fresh_metrics).to_csv(root/'fresh_metrics.csv',index=False)
    pd.DataFrame(predictions).to_csv(root/'PRIVATE_per_material_predictions.csv',index=False)
    pd.DataFrame(recipes).to_csv(root/'recipe_roundtrip.csv',index=False)
    pd.DataFrame(lower_level).to_csv(root/'scan_reference_audit.csv',index=False)
    success=bool(comparisons.final_rule_status.eq('MATCH').all() and comparisons.score_status.eq('MATCH').all() and families.status.eq('MATCH').all() and all(x['status']=='MATCH' for x in recipes))
    if not comparisons.loc[comparisons.protocol=='paper','old_snapshot_mask_equal'].all(): success=False
    if any(x['status']!='MATCH' for x in lower_level if x['kind']=='used_prefix'): success=False
    if write_pretrained is None and not comparisons.bundled_mask_equal.fillna(False).all(): success=False
    # Accompanying output versions are checked for semantic agreement, not used to fit.
    supplements=[]
    for name in SUPPLEMENTS:
        try:
            archive=ReferenceArchive(reference_dir,name);manifest=archive.json('supplement_manifest.json')
            record={**archive.identity(),'status':'READ','manifest':manifest}
            if name.endswith('_v14'):
                other=archive.csv(FAMILY);current=ea.csv(FAMILY)
                record['family_table_equal_v15']=bool(other.equals(current))
                if not record['family_table_equal_v15']:success=False
            if name.endswith('_v13'):
                per=archive.csv('PRIMARY_STCA_family_full_pipeline_permutation.csv')
                record['columns']=list(per.columns)
                record['interpretation']='Full-pipeline resampling statistics, not additional training data.'
            if name=='reviewer_ready_thermal_gap_supplement_outputs':
                record['interpretation']='Source-only locked alternative-split analyses; not interchangeable with historical core best selection.'
            supplements.append(record)
        except FileNotFoundError:
            supplements.append({'archive':name,'status':'NOT_SUPPLIED'})
    pd.DataFrame([{'property':'Tg','n':len(tx),'inter_n':int(ttrain.sum()),'extra_n':int((~ttrain).sum()),'unit':'degC','split':'explicit PID labels'},
                  {'property':'EC','n':len(ex),'inter_n':int(etrain.sum()),'extra_n':int((~etrain).sum()),'unit':'log10(S/cm)','split':'row-order reconstruction, all archived family/scope counts checked'}]).to_csv(root/'input_audit.csv',index=False)
    status={'package_version':PACKAGE_VERSION,'python':sys.version,'platform':platform.platform(),
        'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,'rdkit':tchem.attrs['rdkit_version'],
        'status':'PASS_RULE_FAMILY_SCORE_PARITY' if success else 'FAIL',
        'paper_final_rules_matched':int(comparisons[(comparisons.protocol=='paper')&(comparisons.final_rule_status=='MATCH')].shape[0]),
        'paired_source_locked_rules_matched':int(comparisons[(comparisons.protocol=='source_locked')&(comparisons.final_rule_status=='MATCH')].shape[0]),
        'archived_rule_scope_metric_rows_checked':len(data_checks),'archived_rule_scope_metric_rows_matched':int(data_checks.status.eq('MATCH').sum()),
        'archives':[ta.identity(),ea.identity()],'supplements':supplements,
        'scope_limitations':['Not an untouched-test estimate or a new independent performance benchmark: paper selection uses historical extra labels.',
          'Original raw fingerprint CSVs and their row order are not in these result archives.',
          'EC split rebuilt from 691 first rows and 172 following rows, independently gated against all 171 archived family/scope metric records.',
          'Thermal historical precomputed correlation coefficients are not numerically identical to the fresh value-grid scan; used top-10 rankings, families, winners and performance metrics agree.',
          'Alternative-split, cross-property epsilon/Tm/Td/TC, bootstrap and permutation analyses are not rerun by this core parity check.'],
        'inference_uses_reference_results':False,'expected_winner_used_during_fit':False}
    dump_json(root/'status.json',status)
    if not success:raise STCAError('Rule/family/score audit failed; models were not promoted.')
    if write_pretrained is not None:
        dest=Path(write_pretrained);dest.mkdir(parents=True,exist_ok=True)
        for (profile,protocol),model in artifacts.items():
            model.save(dest/f'{profile.replace("-","_")}_{protocol}_refit.json',overwrite=True)
        # Compact verified-result record; no measurement rows/PIDs/SMILES.
        dump_json(dest/'verified_refit_summary.json',{'schema':'stca-verified-refit-v1','status':status['status'],
            'package_version':PACKAGE_VERSION,'environment':{k:status[k] for k in ('python','platform','numpy','pandas','scipy','rdkit')},
            'rows':comparisons.drop(columns=['bundled_signature','bundled_mask_equal']).to_dict('records'),
            'scope_limitations':status['scope_limitations'],'input_archives':status['archives']},overwrite=True)
    print(comparisons[['profile','protocol','tier','final_rule_status','recomputed_score','score_abs_error']].to_string(index=False))
    print(f'Final rule/family/metric parity passed. Reports: {root}')
    return status


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-dir',required=True,help='Directory containing the supplied output ZIPs or extracted folders.')
    p.add_argument('--output',required=True,help='New, empty result directory. May contain private evaluation records.')
    a=p.parse_args(argv)
    try:run(a.reference_dir,a.output);return 0
    except (STCAError,FileNotFoundError,FileExistsError,KeyError,ValueError,zipfile.BadZipFile) as exc:
        print('Verification failed: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
