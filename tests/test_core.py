# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

import json
import math
import numpy as np
import pandas as pd
import pytest
from scipy.stats import pearsonr

from stca import (STCA,ScanConfig,Rule,ScreeningModel,scan_frequencies,signed_rankings,
                  signed_prefix_rules,load_pretrained,list_profiles,grouped_holdout,
                  fingerprints_from_strings,ec_to_log10_s_cm,STCAError,
                  NoValidRuleError,ArchivedProfileWarning,strict_harmonic,screening_metrics,
                  load_legacy_pair,rule_from_signature,import_legacy_rule)
from stca.chemistry import MACCS_NAMES,MACCS_SPEC,maccs_from_smiles
from stca.metrics import labels_at,target_cutoff


def toy(n=240,p=6,seed=17):
    rng=np.random.default_rng(seed)
    X=rng.integers(0,2,(n,p),dtype=np.uint8)
    y=9*X[:,0].astype(float)-7*X[:,1]+1.5*X[:,2]+rng.normal(0,.4,n)
    return X,y


@pytest.mark.parametrize('direction',['high','low'])
@pytest.mark.parametrize('mode',['value','unique','quantile'])
def test_scan_matches_naive(direction,mode):
    X,y=toy(n=60)
    cfg=ScanConfig(mode=mode,step=.25,min_subset_size=2)
    r=scan_frequencies(X,y,direction=direction,config=cfg)
    score=y if direction=='high' else -y
    frequencies=np.array([X[score>=t].mean(axis=0) for t in r.thresholds])
    counts=np.array([np.sum(score>=t) for t in r.thresholds])
    np.testing.assert_allclose(r.frequencies,frequencies,atol=1e-14)
    np.testing.assert_array_equal(r.counts,counts)
    for row in r.table.itertuples():
        expected=pearsonr(r.thresholds,frequencies[:,row.key]).statistic
        np.testing.assert_allclose(row.correlation,expected,atol=1e-12)


def test_scan_truncation_is_reported():
    X,y=toy()
    r=scan_frequencies(X,y,config=ScanConfig(step=.01,max_points=20))
    assert r.truncated and len(r.thresholds)<=20


@pytest.mark.parametrize('X,y',[([[0],[1]],[1,2]),([[0],[1],[0],[1]],[1,1,1,1]),
                             ([[0],[2],[0],[1]],[1,2,3,4]),([[0],[1],[0],[1]],[1,2,np.nan,4])])
def test_invalid_fit_inputs(X,y):
    with pytest.raises(STCAError): STCA().fit(X,y)


@pytest.mark.parametrize('keys,values',[((),()),((1,1),(1,0)),((-1,),(1,)),((1,),(2,)),((1.1,),(1,)),((True,),(1,))])
def test_invalid_rules(keys,values):
    with pytest.raises(STCAError): Rule(keys,values)


def test_signed_prefix_count_and_meaning():
    rules=signed_prefix_rules(list(range(10)),list(range(10,20)),10)
    assert len(rules)==120
    r=next(x for x in rules if x.name=='Top2_positive_plus_Top3_negative')
    assert r.keys==(0,1,10,11,12) and r.values==(1,1,0,0,0)
    X=np.zeros((2,20),int);X[:,0:2]=1;X[1,10]=1
    np.testing.assert_array_equal(r.apply(X),[True,False])


def test_ec_roles_swapped_exactly_once():
    X,y=toy()
    params=dict(tiers=(.2,),hierarchy='ec_reverse',scan=ScanConfig(step=.1),max_rank=5,mcc_mode='nonnegative')
    low=STCA(direction='low',**params).fit(X,y)
    high=STCA(direction='high',**params).fit(X,y)
    assert low.artifact['signed_rankings']['positive_keys']==high.artifact['signed_rankings']['negative_keys']
    assert low.artifact['signed_rankings']['negative_keys']==high.artifact['signed_rankings']['positive_keys']
    assert high.provenance['ec_roles_swapped_once'] is True
    p=low.artifact['signed_rankings']['positive_keys'][:2]
    n=low.artifact['signed_rankings']['negative_keys'][:2]
    r1=Rule(tuple(p+n),(0,)*len(p)+(1,)*len(n))
    r2=Rule(tuple(n+p),(1,)*len(n)+(0,)*len(p))
    np.testing.assert_array_equal(r1.apply(X),r2.apply(X))


def test_nominal_fallback_is_explicit():
    X,y=toy()
    r=scan_frequencies(X,y)
    r.table['nominal_p_value']=1
    pos,neg,info=signed_rankings(r,ScanConfig(nominal_filter='legacy_both_signs'))
    assert pos and neg and not info['nominal_filter_applied']
    pos,neg,info=signed_rankings(r,ScanConfig(nominal_filter='strict'))
    assert not pos and not neg and info['nominal_filter_applied']


def test_save_load_exact_and_no_overwrite(tmp_path):
    X,y=toy()
    model=STCA(tiers=(.2,),scan=ScanConfig(step=.1)).fit(X,y)
    path=tmp_path/'model.json';model.save(path)
    other=ScreeningModel.load(path)
    assert model.artifact==other.artifact
    pd.testing.assert_frame_equal(model.screen_fingerprints(X,tier=.2),other.screen_fingerprints(X,tier=.2))
    with pytest.raises(FileExistsError): model.save(path)


def test_evaluation_never_changes_model():
    X,y=toy()
    model=STCA(tiers=(.2,)).fit(X[:160],y[:160])
    frozen=model.artifact
    model.evaluate(X[160:],y[160:],tier=.2)
    model.evaluate(X[160:],y[160:][::-1],tier=.2,cutoff_mode='dataset_relative')
    assert model.artifact==frozen
    assert model.provenance['external_labels_used_for_fit'] is False


def test_train_cutoff_not_recomputed_on_test():
    X,y=toy()
    m=STCA(tiers=(.2,)).fit(X[:160],y[:160])
    fixed=m.evaluate(X[160:],y[160:]+100,tier=.2)
    relative=m.evaluate(X[160:],y[160:]+100,tier=.2,cutoff_mode='dataset_relative')
    assert fixed['cutoff']==m.artifact['tiers']['0.2']['train_cutoff']
    assert relative['cutoff']>fixed['cutoff']+90
    assert fixed['positive_n']==len(X[160:]) and not fixed['valid_screen']


def test_dataframe_column_order_is_aligned_by_name():
    X,y=toy();frame=pd.DataFrame(X,columns=list('abcdef'))
    m=STCA(tiers=(.2,)).fit(frame,y)
    pd.testing.assert_frame_equal(m.screen_fingerprints(frame),m.screen_fingerprints(frame[list('fedcba')]))
    with pytest.raises(STCAError): m.screen_fingerprints(frame.rename(columns={'a':'wrong'}))


def test_constant_features_removed():
    X,y=toy();X[:,4]=1;X[:,5]=0
    table=scan_frequencies(X,y).table
    assert 4 not in table.key.values and 5 not in table.key.values


def test_nominal_tier_ties_are_inclusive():
    y=[0,1,1,1,1]
    cutoff=target_cutoff(y,.2,'high')
    assert cutoff==1 and labels_at(y,cutoff,'high').sum()==4


def test_metrics_known_confusion():
    m=screening_metrics([1,1,0,0],[1,0,1,0])
    assert [m[k] for k in ('tp','fp','tn','fn')]==[1,1,1,1]
    assert m['f1']==.5 and m['precision']==.5 and m['mcc']==0
    assert not m['valid_screen']


def test_strict_harmonic_does_not_drop_invalid():
    assert strict_harmonic([.5,1])==pytest.approx(2/3)
    assert strict_harmonic([.5,None]) is None
    assert strict_harmonic([.5,0]) is None
    assert strict_harmonic([.5,1],[True,False]) is None
    with pytest.raises(STCAError):strict_harmonic([1,2],[True])


@pytest.mark.parametrize('unit,values',[('S/cm',[1e-12,1e-8]),('S/m',[1e-10,1e-6]),
                                      ('log10(S/cm)',[-12,-8]),('log10(S/m)',[-10,-6])])
def test_ec_units(unit,values):
    np.testing.assert_allclose(ec_to_log10_s_cm(values,unit),[-12,-8])


def test_negative_raw_ec_rejected():
    with pytest.raises(STCAError):ec_to_log10_s_cm([-12,-8],'S/cm')


def test_archived_warning_and_cutoff_guard():
    with pytest.warns(ArchivedProfileWarning): m=load_pretrained('tg',protocol='legacy_snapshot')
    X=np.zeros((3,167),int)
    with pytest.raises(STCAError,match='no verified numerical'):m.evaluate(X,[1,2,3],tier=.2)
    with pytest.raises(STCAError):m.rule_for(.25)
    assert m.provenance['original_full_pipeline_reproduced_in_this_package'] is False


@pytest.mark.parametrize('name',['tg-high','ec-low','ec-high'])
def test_stock_masks_match_transcribed_literals(name):
    m=load_pretrained(name,warn=False)
    rng=np.random.default_rng(99);X=rng.integers(0,2,(500,167));X[:,0]=0
    for tier in m.tiers:
        r=m.rule_for(tier)
        if name=='ec-high':pos=[36];neg=[]
        elif name=='ec-low':pos=[163];neg=[26,36,39,40,48,49,73,88,102,124,130]
        else:pos=[142] if tier in (.2,.3) else [];neg=[90,91,93,118,123,128,129,147]+([155] if tier==.1 else [])
        expected=np.array([all(row[k]==1 for k in pos) and all(row[k]==0 for k in neg) for row in X])
        np.testing.assert_array_equal(m.screen_fingerprints(X,tier=tier).selected,expected)
        # One satisfying witness plus one failing witness for each required literal.
        witness=np.zeros((1+len(pos)+len(neg),167),int);witness[:,pos]=1
        for i,k in enumerate(pos+neg,1):witness[i,k]=1-witness[i,k]
        assert m.screen_fingerprints(witness,tier=tier).selected.tolist()==[True]+[False]*(len(pos)+len(neg))
    assert len(list_profiles())==11


def test_maccs_layout_explicit():
    s='0'*166
    with pytest.raises(STCAError):fingerprints_from_strings([s])
    a=fingerprints_from_strings([s],layout='maccs166_keys1to166')
    assert a.shape==(1,167)
    with pytest.raises(STCAError):fingerprints_from_strings(['1'+'0'*166])


def test_smiles_invalid_never_matches_absence_rules():
    pytest.importorskip('rdkit')
    m=load_pretrained('tg',warn=False)
    result=m.screen(['CC','not_smiles','','*','*CC*'],tier=.1,errors='report')
    assert result.input_valid.tolist()==[True,False,False,False,True]
    assert result.loc[1:3,'selected'].isna().all()
    with pytest.raises(STCAError):m.screen(['not_smiles'],tier=.1)


def test_smiles_known_rdkit_bits():
    pytest.importorskip('rdkit')
    from rdkit import Chem,DataStructs
    from rdkit.Chem import MACCSkeys
    smiles=['CC','c1ccccc1','*CCO*']
    X,_=maccs_from_smiles(smiles)
    for row,s in zip(X,smiles):
        assert ''.join(map(str,row))==MACCSkeys.GenMACCSKeys(Chem.MolFromSmiles(s)).ToBitString()


def test_group_split_and_evaluation_leakage_guard():
    groups=np.repeat(np.arange(30),2)
    tr,te=grouped_holdout(groups,test_fraction=.2,seed=42)
    assert not set(groups[tr])&set(groups[te])
    X,y=toy(n=60)
    m=STCA(tiers=(.2,)).fit(X[tr],y[tr],groups=groups[tr])
    assert m.evaluate(X[te],y[te],groups=groups[te])['group_overlap_audit']=='disjoint'
    with pytest.raises(STCAError,match='overlap'):m.evaluate(X[tr],y[tr],groups=groups[tr])
    with pytest.raises(STCAError,match='Supply evaluation groups'):m.evaluate(X[te],y[te])


def test_legacy_join_checks_id_not_position(tmp_path):
    fp=tmp_path/'fp.csv';prop=tmp_path/'y.csv'
    fp.write_text('a,'+'0'*167+'\nb,'+'0'*36+'1'+'0'*130+'\n')
    prop.write_text('b,20\na,10\n')
    X,y,ids=load_legacy_pair(fp,prop)
    assert ids.tolist()==['a','b'] and y.tolist()==[10,20] and X[1,36]==1
    prop.write_text('a,10\nc,20\n')
    with pytest.raises(STCAError):load_legacy_pair(fp,prop)


def test_rule_signature_safe_parser():
    assert rule_from_signature('STCA|AND|K36=1&K163=0').keys==(36,163)
    for s in ['STCA|AND|','STCA|AND|K36=1&K36=0','STCA|AND|__import__("os")','XGB|AND|K36=1']:
        with pytest.raises(STCAError):rule_from_signature(s)


def test_explicit_legacy_row_import(tmp_path):
    f=tmp_path/'rules.csv'
    pd.DataFrame([{'method':'STCA','percentile':80,'pattern_name':'r1','pattern_signature':'STCA|AND|K36=1',
                   'keys':'[36]','values':'[1]'}]).to_csv(f,index=False)
    m=import_legacy_rule(f,row_index=0,tier=.2,direction='high',target_name='EC',target_unit='log10(S/cm)',
                         selection_provenance='Explicit source-selected row')
    assert m.rule_for(.2).keys==(36,)
    with pytest.raises(STCAError):import_legacy_rule(f,row_index=0,tier=.1,direction='high',target_name='EC',target_unit='log10(S/cm)',selection_provenance='x')


def test_artifact_validation_rejects_dummy_and_unknown_schema():
    obj=load_pretrained('tg',warn=False).artifact
    obj['schema_version']=99
    with pytest.raises(STCAError):ScreeningModel(obj)
    obj['schema_version']=1
    obj['tiers']['0.2']['rules'][0]['rule']['keys'][0]=0
    with pytest.raises(STCAError):ScreeningModel(obj)


def test_no_valid_rule_abstains():
    obj=load_pretrained('tg',warn=False).artifact
    obj['tiers']['0.2']['selected_rule']=None
    m=ScreeningModel(obj)
    with pytest.raises(NoValidRuleError):m.screen_fingerprints(np.zeros((2,167),int),tier=.2)


def test_model_artifact_is_defensive_copy():
    m=load_pretrained('ec-high',warn=False);obj=m.artifact
    obj['tiers']['0.2']['rules'][0]['rule']['values'][0]=0
    assert m.rule_for(.2).values==(1,)


def test_smiles_training_roundtrip_and_failed_refit_clears_state(tmp_path):
    """Synthetic targets test the SMILES training API, not material performance."""
    pytest.importorskip('rdkit')
    smiles=['C','CC','CCC','CCCC','CCCCC','CCCCCC','CO','CCO','CCCO','CCCCO',
            'COC','CCOC','CN','CCN','CCCN','CCCCN','CNC','CCNC',
            'c1ccccc1','Cc1ccccc1','CCc1ccccc1','Oc1ccccc1','Nc1ccccc1','COc1ccccc1',
            'Clc1ccccc1','Fc1ccccc1','c1ccncc1','c1ccoc1','c1ccsc1','c1ccc2ccccc2c1']
    X,_=maccs_from_smiles(smiles)
    y=20*X[:,162].astype(float)-9*X[:,151]+np.arange(len(smiles))*.1
    trainer=STCA(tiers=(.2,),scan=ScanConfig(step=.25),target_name='SYNTHETIC',target_unit='arbitrary')
    model=trainer.fit_smiles(smiles[:24],y[:24])
    assert model.artifact['feature_spec']['kind']=='rdkit_maccs167'
    assert model.provenance['n_source_records']==24
    model.save(tmp_path/'smiles_model.json')
    loaded=ScreeningModel.load(tmp_path/'smiles_model.json')
    np.testing.assert_array_equal(model.screen(smiles[24:]).selected,
                                  loaded.screen(smiles[24:]).selected)
    before=loaded.artifact
    metrics=loaded.evaluate_smiles(smiles[24:],y[24:])
    assert metrics['group_overlap_audit']=='disjoint'
    assert metrics['n']==6 and before==loaded.artifact
    with pytest.raises(STCAError,match='overlap'):
        loaded.evaluate_smiles(smiles[:4],y[:4])
    with pytest.raises(STCAError):
        trainer.fit_smiles(['invalid_smiles'],[1.0])
    assert trainer.model_ is None and trainer.scan_result_ is None
    with pytest.raises(STCAError): trainer.export_diagnostics(tmp_path/'failed_refit')


def test_core_import_and_archive_fingerprint_screen_do_not_import_rdkit():
    import subprocess,sys
    code='''
import sys, importlib.abc
class BlockRDKit(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "rdkit" or fullname.startswith("rdkit."):
            raise ImportError("RDKit deliberately unavailable in this process")
sys.meta_path.insert(0, BlockRDKit())
import numpy as np
import stca
model = stca.load_pretrained("ec-high", warn=False)
X = np.zeros((2,167), dtype=int)
X[1,36] = 1
assert model.screen_fingerprints(X).selected.tolist() == [False,True]
assert not any(k == "rdkit" or k.startswith("rdkit.") for k in sys.modules)
'''
    subprocess.run([sys.executable,'-c',code],check=True)
