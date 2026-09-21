# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
"""Synthetic algorithm fixtures, not experimental Tg/EC performance results."""
from dataclasses import replace
from pathlib import Path
import json
import subprocess
import sys
import numpy as np
import pandas as pd
import pytest
from stca import STCA,ScanConfig,SelectionData,TemplateFamily,ScreeningModel,load_pretrained
from stca.errors import STCAError
from stca.metrics import strict_harmonic
from stca.paper_audit import audit_bundled_rules
from stca.resampling import full_pipeline_resampling
from stca.reproduction import load_manifest_data,find_family,main as replay_main,PRIMARY


def fixture():
    rng=np.random.default_rng(18)
    X=rng.integers(0,2,(120,10),dtype=np.uint8)
    E=rng.integers(0,2,(90,10),dtype=np.uint8)
    y=3*X[:,0].astype(float)+X[:,1]-2*X[:,2]+.8*X[:,3]+rng.normal(0,.25,len(X))
    z=3*E[:,1].astype(float)-2*E[:,2]+.5*E[:,0]+rng.normal(0,.25,len(E))
    return X,y,E,z


def basic(**kw):
    return STCA(tiers=(.3,),scan=ScanConfig(step=.25,nominal_filter='none'),max_rank=4,**kw)


def templates(profile='ec-low',tiers=(.2,),n=3,signature=None):
    items=[{'name':f'family_{i}','positive_n':1,'negative_n':i} for i in range(n)]
    if signature:items[0]['reference_signature']=signature
    return TemplateFamily({'schema':'stca-prefix-family-v1','profile':profile,
        'tiers':{format(t,'.12g'):items for t in tiers},'provenance':{'kind':'synthetic_test_fixture'}})


def test_source_as_remains_only_source_and_final_selection_oracle():
    X,y,E,z=fixture(); t=basic();m=t.fit(X,y)
    tab=t.candidate_table_; valid=tab[tab.in_retained_family & tab.valid_screen]
    best=valid.loc[valid.average_score.idxmax()]
    assert m.rule_for(.3).signature==best.signature
    assert not m.provenance['external_labels_used_for_fit']
    with pytest.raises(STCAError,match='refuses'):
        t.fit(X,y,selection_data=SelectionData(E,z))
    assert t.model_ is None


def test_harmonic_final_selection_matches_independent_scalar_oracle():
    X,y,E,z=fixture();t=basic(selection='core_harmonic')
    m=t.fit(X,y,selection_data=SelectionData(E,z),acknowledge_selection_labels=True)
    entry=m.artifact['tiers']['0.3']; scored=[]
    for rec in entry['rules']:
        mm=rec['selection_scope_metrics']; vals=[mm[k]['average_score'] for k in ('source','comparison','combined')]
        ok=all(mm[k]['valid_screen'] for k in mm)
        expected=3/sum(1/v for v in vals) if ok and min(vals)>0 else None
        assert rec['selection_score']==pytest.approx(expected) if expected is not None else rec['selection_score'] is None
        if expected is not None: scored.append((expected,-rec['source_family_rank'],rec['rule']['name']))
    assert entry['selected_rule']==max(scored)[2]
    assert m.provenance['external_labels_used_for_fit']
    assert not m.provenance['comparison_is_untouched_test']


def test_source_and_harmonic_can_choose_different_rules_but_same_rankings():
    X,y,E,z=fixture();a=basic();b=basic(selection='core_harmonic')
    ma=a.fit(X,y);mb=b.fit(X,y,selection_data=SelectionData(E,z),acknowledge_selection_labels=True)
    assert ma.artifact['signed_rankings']==mb.artifact['signed_rankings']
    assert ma.rule_for(.3).signature!=mb.rule_for(.3).signature


@pytest.mark.parametrize('mode',['validation_as','core_harmonic'])
def test_external_selection_requires_explicit_acknowledgment(mode):
    X,y,E,z=fixture()
    with pytest.raises(STCAError,match='acknowledge'):
        basic(selection=mode).fit(X,y,selection_data=SelectionData(E,z))


def test_selection_groups_cannot_be_reported_as_new_test_after_save(tmp_path):
    X,y,E,z=fixture();t=basic(selection='core_harmonic')
    ids=[f's{i}' for i in range(len(y))]; es=[f'e{i}' for i in range(len(z))]
    m=t.fit(X,y,groups=ids,selection_data=SelectionData(E,z,es),acknowledge_selection_labels=True)
    path=tmp_path/'m.json';m.save(path);r=ScreeningModel.load(path)
    with pytest.raises(STCAError,match='overlap'):r.evaluate(E,z,tier=.3,groups=es)
    q=r.evaluate(E,z,tier=.3,groups=es,allow_overlap=True)
    assert q['evaluation_role']=='selection_data_reassessment'


def test_source_selection_overlap_blocked():
    X,y,E,z=fixture()
    with pytest.raises(STCAError,match='overlap'):
        basic(selection='core_harmonic').fit(X,y,groups=np.arange(len(y)),
            selection_data=SelectionData(E,z,np.arange(len(z))),acknowledge_selection_labels=True)


@pytest.mark.parametrize('scores,flags',[([.5,.4,None],[True]*3),([.5,.4,0],[True]*3),([.5,.4,.3],[True,False,True])])
def test_harmonic_does_not_drop_missing_invalid_or_zero(scores,flags):
    assert strict_harmonic(scores,flags) is None


def test_imported_reference_is_not_used_as_discovered_literal():
    f=templates(signature='STCA|AND|K163=1')
    rules,audit=f.instantiate(.2,[7,8],[3,4,5])
    assert rules[0].signature=='STCA|AND|K7=1'
    assert audit[0]['reference_match'] is False


def test_template_missing_policy_is_explicit():
    f=templates()
    with pytest.raises(STCAError,match='Insufficient'):f.instantiate(.2,[5],[2])
    _,a=f.instantiate(.2,[5],[2],missing='truncate')
    assert a[-1]['template_truncated']


def test_template_family_is_not_replaced_with_top8():
    X,y,E,z=fixture();f=templates('tg-high',(.3,),n=4)
    t=basic(template_family=f,family_size=3)
    m=t.fit(X,y)
    assert len(m.artifact['tiers']['0.3']['rules'])==4
    assert t.candidate_table_.in_retained_family.all()


def test_complete_primary_import_ignores_metric_columns(tmp_path):
    rows=[]
    for i,(pn,nn) in enumerate([(1,0),(0,1),(1,1)]):
        keys=([163] if pn else [])+([36] if nn else [])
        vals=([1] if pn else [])+([0] if nn else [])
        sig='STCA|AND|'+'&'.join(f'K{k}={v}' for k,v in sorted(zip(keys,vals)))
        rows.append(dict(method='STCA',regime='insulation',percentile=80,pattern_name=f't{i}',
            pattern_signature=sig,keys=str(keys),values=str(vals),H_EC_core=.99-i))
    p=tmp_path/'family.csv';pd.DataFrame(rows).to_csv(p,index=False)
    a=TemplateFamily.from_primary_csv(p,profile='ec-low')
    for r in rows:r['H_EC_core']=12345
    pd.DataFrame(rows).to_csv(p,index=False)
    b=TemplateFamily.from_primary_csv(p,profile='ec-low')
    assert a.document['tiers']==b.document['tiers']
    assert len(a.document['tiers']['0.2'])==3
    assert a.document['provenance']['sha256']!=b.document['provenance']['sha256']


def test_ambiguous_labels_alone_are_not_expanded(tmp_path):
    p=tmp_path/'f.csv';pd.DataFrame([dict(method='STCA',regime='insulation',percentile=80,pattern_name='top 11~20 neg')]).to_csv(p,index=False)
    with pytest.raises(STCAError,match='Missing complete'):TemplateFamily.from_primary_csv(p,profile='ec-low')


@pytest.mark.parametrize('profile',['ec-low','ec-high'])
def test_electrical_primary_refuses_single_pretrained_as_family(profile):
    with pytest.raises(STCAError,match='complete'):STCA.for_profile(profile,protocol='electrical_primary')


@pytest.mark.parametrize('profile,step,rank,direction',[('tg-high',1.,10,'high'),('ec-low',.01,35,'low'),('ec-high',.01,35,'high')])
def test_profile_defaults(profile,step,rank,direction):
    t=STCA.for_profile(profile)
    assert (t.scan.step,t.max_rank,t.direction)==(step,rank,direction)
    assert t.selection=='core_harmonic'


def test_ec_role_exchange_exactly_once():
    X,y,E,z=fixture();lo=STCA.for_profile('ec-low',protocol='generic',tiers=(.2,),scan=ScanConfig(step=.25,nominal_filter='none'))
    hi=STCA.for_profile('ec-high',protocol='generic',tiers=(.2,),scan=ScanConfig(step=.25,nominal_filter='none'))
    a=lo.fit(X,y);b=hi.fit(X,y)
    assert a.artifact['signed_rankings']['positive_keys']==b.artifact['signed_rankings']['negative_keys']
    assert a.artifact['signed_rankings']['negative_keys']==b.artifact['signed_rankings']['positive_keys']
    assert not a.provenance['ec_roles_swapped_once'] and b.provenance['ec_roles_swapped_once']


def test_reference_table_is_independent_literal_check():
    audit=audit_bundled_rules();assert len(audit)==11
    assert audit.literal_status.eq('MATCH').all()
    assert audit.snapshot_bytes_status.eq('UNCHANGED').all()
    # Constants transcribed from the SI, not obtained by fit or list_profiles.
    low=load_pretrained('ec-low',warn=False).rule_for(.2)
    assert set(k for k,v in zip(low.keys,low.values) if v)=={163}
    assert set(k for k,v in zip(low.keys,low.values) if not v)=={26,36,39,40,48,49,73,88,102,124,130}
    assert audit.numerical_refit_status.eq('NOT_EVALUATED_NO_RAW_DATA').all()


@pytest.mark.parametrize('kind',['bootstrap','permutation'])
def test_resampling_reruns_discovery_and_labels_status(kind):
    X,y,E,z=fixture();t=basic(selection='core_harmonic')
    r,s=full_pipeline_resampling(t,(X,y),(E,z),kind=kind,repeats=5,seed=18,
        feature_names=[f'f{i}' for i in range(10)],feature_spec={'kind':'binary','n_features':10})
    assert len(r)==5 and len(s)==1
    assert s.valid_repeats.iloc[0]+s.invalid_repeats.iloc[0]==5
    assert not s.exact_historical_rng_reproduction.iloc[0]
    if kind=='permutation':
        assert s.p_lower_bound.iloc[0]<=s.p_upper_bound.iloc[0]


def test_explicit_core_all_not_silently_replaced():
    X,y,E,z=fixture();a=np.vstack([X,E]);b=np.concatenate([y,z]);ids=[f'p{i}' for i in range(len(b))]
    t=basic(selection='core_harmonic')
    m=t.fit(X,y,groups=ids[:len(y)],selection_data=SelectionData(E,z,ids[len(y):]),
        combined_data=SelectionData(a,b,ids),acknowledge_selection_labels=True)
    assert m.provenance['core_all_source']=='explicit_membership_audited_table'
    with pytest.raises(STCAError,match='membership'):
        t.fit(X,y,groups=ids[:len(y)],selection_data=SelectionData(E,z,ids[len(y):]),
            combined_data=SelectionData(a,b,['wrong']*len(b)),acknowledge_selection_labels=True)


def make_realdata_manifest_fixture(tmp_path):
    """Deliberately synthetic input files for I/O integrity, not a scientific dataset."""
    from hashlib import sha256
    X,y,E,z=fixture();cfg={};input_files=[]
    run=tmp_path/'run';(run/'realdata').mkdir(parents=True)
    for prop in ['tg','ec']:
        root=tmp_path/prop;root.mkdir();cfg[prop+'_dir']=str(root)
        cfg.update({prop+'_layout':'maccs167',prop+'_header':'none',prop+'_step':.25,prop+'_max_rank':4,
                    prop+'_unit':'degC' if prop=='tg' else 'log10(S/cm)'})
        for split,stem,a,b in [('train','normal',X,y),('test','outliers',E,z)]:
            full=np.zeros((len(a),167),dtype=np.uint8);full[:,1:11]=a
            ids=[f'{prop}_{split}_{i}' for i in range(len(a))]
            fp=root/f'morgen_{stem}_maccs_fingerprint.csv';yp=root/f'morgen_{stem}_{prop}.csv'
            pd.DataFrame({'id':ids,'fp':[''.join(map(str,row)) for row in full]}).to_csv(fp,index=False,header=False)
            pd.DataFrame({'id':ids,'y':b}).to_csv(yp,index=False,header=False)
            for p in (fp,yp):input_files.append({'property':prop,'split':split,'file':p.name,'sha256':sha256(p.read_bytes()).hexdigest()})
    m={'config':cfg,'input_files':input_files}
    (run/'realdata/run_manifest.json').write_text(json.dumps(m))
    return run,m


def test_replay_uses_all_eight_original_inputs_and_checks_hashes(tmp_path):
    run,m=make_realdata_manifest_fixture(tmp_path)
    data,a=load_manifest_data(m);assert len(a)==8
    assert data['tg']['train'][0].shape==(120,167)
    p=Path(m['config']['ec_dir'])/'morgen_normal_ec.csv';p.write_text(p.read_text()+'\n')
    with pytest.raises(STCAError,match='INPUT_CHANGED'):load_manifest_data(m)


def test_replay_pretrained_only_does_not_require_core_or_family(tmp_path):
    run,_=make_realdata_manifest_fixture(tmp_path);out=tmp_path/'out'
    assert replay_main(['--run-dir',str(run),'--output',str(out),'--mode','screen_only'])==0
    status=json.loads((out/'status.json').read_text());assert not status['errors']
    assert len(status['tasks'])==3
    assert not status['automatic_certification']
    assert len(pd.read_csv(out/'final_rule_parity.csv'))==11


def test_missing_family_reported_not_replaced(tmp_path):
    run,_=make_realdata_manifest_fixture(tmp_path);out=tmp_path/'out'
    assert replay_main(['--run-dir',str(run),'--output',str(out)])==2
    status=json.loads((out/'status.json').read_text())
    missing=[r for r in status['tasks'] if r['status']=='REFERENCE_FAMILY_MISSING']
    assert {r['task'] for r in missing}=={'ec-low','ec-high'}


def test_new_commands_are_executable(tmp_path):
    r=subprocess.run([sys.executable,'-m','stca','paper-audit'],capture_output=True,text=True)
    assert r.returncode==0 and 'Run verify-results' in r.stdout
    X,y,_,_=fixture();p=tmp_path/'data.csv';df=pd.DataFrame(X,columns=[f'f{i}' for i in range(10)]);df['y']=y;df.to_csv(p,index=False)
    r=subprocess.run([sys.executable,'-m','stca','train-profile','--profile','tg-high','--protocol','generic','--input',str(p),
        '--target','y','--features',','.join(df.columns[:-1]),'--output-dir',str(tmp_path/'model')],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert (tmp_path/'model/model.json').is_file()

@pytest.mark.parametrize('profile,tier,present,absent',[
    *[('tg-high',t,{142},{90,91,93,118,123,128,129,147}) for t in (.3,.2)],
    ('tg-high',.1,set(),{90,91,93,118,123,128,129,147,155}),
    *[('ec-low',t,{163},{26,36,39,40,48,49,73,88,102,124,130}) for t in (.2,.15,.1,.05)],
    *[('ec-high',t,{36},set()) for t in (.2,.15,.1,.05)],
])
def test_all_eleven_si_literal_rows(profile,tier,present,absent):
    # Literal constants are transcribed from the SI table, independent of fit().
    r=load_pretrained(profile,warn=False).rule_for(tier)
    assert {k for k,v in zip(r.keys,r.values) if v==1}==present
    assert {k for k,v in zip(r.keys,r.values) if v==0}==absent


def test_replay_compares_same_complete_family_with_and_without_external_selection(tmp_path):
    run,m=make_realdata_manifest_fixture(tmp_path);p=Path(m['config']['ec_dir'])/PRIMARY
    rows=[]
    for regime in ['insulation','conduction']:
        for percentile in [80,85,90,95]:
            for name,sig in [('one_positive','STCA|AND|K1=1'),('one_negative','STCA|AND|K3=0'),
                             ('mixed','STCA|AND|K1=1&K3=0')]:
                rows.append(dict(method='STCA',regime=regime,percentile=percentile,pattern_name=name,pattern_signature=sig))
    pd.DataFrame(rows).to_csv(p,index=False)
    out=tmp_path/'out'
    assert replay_main(['--run-dir',str(run),'--output',str(out)])==0
    status=json.loads((out/'status.json').read_text());assert not status['errors']
    for task in ['ec-low','ec-high']:
        protocols={r['protocol'] for r in status['tasks'] if r['task']==task}
        assert {'source_locked','template_source_locked','electrical_primary','archived_snapshot'}==protocols
        a=json.loads((out/f'{task}_template_source_locked.json').read_text())
        b=json.loads((out/f'{task}_electrical_primary.json').read_text())
        assert not a['provenance']['external_labels_used_for_fit']
        assert b['provenance']['external_labels_used_for_fit']
        assert a['signed_rankings']==b['signed_rankings']
