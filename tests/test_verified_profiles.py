"""Recipe/selection regression. The private real-data audit is a separate command."""
import copy
from importlib.resources import files
import json
import subprocess
import sys
import numpy as np
import pandas as pd
import pytest
from stca import STCA, ScanConfig, SelectionData, TemplateFamily, load_pretrained, STCAError, ScreeningModel
from stca.protocols import bundled_primary_family
from stca.verified import independent_metrics, ReferenceArchive
from stca.metrics import screening_metrics

PROFILES=('tg-high','ec-low','ec-high')

@pytest.mark.parametrize('profile',PROFILES)
@pytest.mark.parametrize('protocol',['paper','source_locked'])
def test_paired_pretrained_and_factory_recipe_identical(profile,protocol):
    model=load_pretrained(profile,protocol=protocol,warn=False)
    trainer=model.new_trainer();expected=STCA.for_profile(profile,protocol=protocol)
    for k in ['direction','tiers','scan','hierarchy','selection','max_rank','mcc_mode','protocol_id','comparison_cutoff_mode']:
        assert getattr(trainer,k)==getattr(expected,k)
    if expected.template_family:
        assert expected.template_family.document==trainer.template_family.document
    assert all(t['train_cutoff'] is not None for t in model.artifact['tiers'].values())
    assert model.provenance['external_labels_used_for_fit']==(protocol=='paper')

@pytest.mark.parametrize('profile,counts',[('ec-low',[6,6,6,7]),('ec-high',[8,8,8,8])])
def test_bundled_family_contains_lengths_only(profile,counts):
    doc=bundled_primary_family(profile).document
    assert [len(x) for x in doc['tiers'].values()]==counts
    for records in doc['tiers'].values():
        for rec in records:
            assert not {'reference_signature','keys','values','score','selected','expected_winner'}.intersection(rec)
            assert rec['positive_n']+rec['negative_n']>0

@pytest.mark.parametrize('profile',PROFILES)
def test_default_paper_refuses_missing_selection_labels(profile):
    rng=np.random.default_rng(71);X=rng.integers(0,2,(80,167),dtype=np.uint8);X[:,0]=0;y=rng.normal(size=80)
    with pytest.raises(STCAError,match='acknowledge_selection_labels'):
        STCA.for_profile(profile).fit(X,y)

@pytest.mark.parametrize('profile',PROFILES)
def test_verified_paper_rules_preserve_original_decisions(profile):
    rng=np.random.default_rng(80);X=rng.integers(0,2,(1000,167),dtype=np.uint8);X[:,0]=0
    old=load_pretrained(profile,protocol='legacy_snapshot',warn=False)
    new=load_pretrained(profile,warn=False)
    for tier in new.tiers:
        assert old.rule_for(tier).signature==new.rule_for(tier).signature
        assert np.array_equal(old.rule_for(tier).apply(X),new.rule_for(tier).apply(X))


def test_generic_fit_does_not_read_pretrained(monkeypatch):
    import stca.pretrained as mod
    def forbidden(*args,**kwargs): raise AssertionError('Fit read a pretrained model')
    monkeypatch.setattr(mod,'load_pretrained',forbidden)
    rng=np.random.default_rng(12);X=rng.integers(0,2,(200,6));y=2*X[:,0]-X[:,1]+rng.normal(0,.3,200)
    a=STCA(tiers=(.2,),scan=ScanConfig(step=.2)).fit(X,y)
    b=a.new_trainer().fit(X,y)
    assert a.artifact==b.artifact


def test_templates_ignore_reference_winner_literals():
    rng=np.random.default_rng(17);X=rng.integers(0,2,(220,6));y=3*X[:,0]-2*X[:,1]+rng.normal(0,.4,220)
    base={'schema':'stca-prefix-family-v1','profile':'tg-high','provenance':{'kind':'test'},'tiers':{'0.2':[
        {'name':'one_pos','positive_n':1,'negative_n':0,'reference_signature':'STCA|AND|K5=1'},
        {'name':'one_neg','positive_n':0,'negative_n':1,'reference_signature':'STCA|AND|K4=0'},
        {'name':'mixed','positive_n':1,'negative_n':1,'reference_signature':'STCA|AND|K4=0&K5=1'}]}}
    a=STCA(tiers=(.2,),scan=ScanConfig(step=.2),template_family=TemplateFamily(base)).fit(X,y)
    for rec in base['tiers']['0.2']:rec.pop('reference_signature')
    b=STCA(tiers=(.2,),scan=ScanConfig(step=.2),template_family=TemplateFamily(base)).fit(X,y)
    assert a.rule_for(.2).signature==b.rule_for(.2).signature
    assert a.rule_for(.2).signature!='STCA|AND|K4=0&K5=1'


def test_new_trainer_does_not_copy_winner():
    m=load_pretrained('tg-high',warn=False);changed=m.artifact
    for entry in changed['tiers'].values():entry['selected_rule']=entry['rules'][0]['rule']['name']
    t=ScreeningModel(changed).new_trainer()
    assert t.model_ is None
    assert t.scan_result_ is None
    assert not hasattr(t,'pretrained_rules')
    assert t.selection=='core_harmonic'


def test_legacy_snapshot_has_no_train_recipe():
    with pytest.raises(STCAError,match='no complete training recipe'):
        load_pretrained('tg-high',protocol='legacy_snapshot',warn=False).new_trainer()


def test_metrics_implementation_independent():
    rng=np.random.default_rng(77)
    for _ in range(20):
        y=rng.integers(0,2,37);s=rng.integers(0,2,37)
        a=independent_metrics(y,s);b=screening_metrics(y,s)
        for k,v in a.items():assert v==pytest.approx(b[k],abs=1e-14)


def test_receipt_is_record_of_real_fit_not_full_claim():
    receipt=json.loads(files('stca').joinpath('assets','verified_refit_summary.json').read_text(encoding="utf-8"))
    assert len(receipt['rows'])==22
    assert all(r['final_rule_status']=='MATCH' for r in receipt['rows'])
    assert 'precomputed correlation' in ' '.join(receipt['scope_limitations'])
    assert 'untouched' in ' '.join(receipt['scope_limitations'])


def test_reference_member_traversal_rejected(tmp_path):
    (tmp_path/'sample').mkdir();r=ReferenceArchive(tmp_path,'sample')
    with pytest.raises(STCAError):r.read('../secret')


def test_paper_cli_requires_comparison_before_reading(tmp_path):
    r=subprocess.run([sys.executable,'-m','stca','train-profile','--profile','tg-high','--input','absent.csv',
       '--target','Tg','--output-dir',str(tmp_path/'model')],capture_output=True,text=True)
    assert r.returncode==2 and '--selection-input' in r.stderr
    assert not (tmp_path/'model').exists()


def test_model_json_serializes_full_recipe(tmp_path):
    for profile in PROFILES:
        m=load_pretrained(profile,warn=False);path=tmp_path/(profile+'.json');m.save(path)
        other=ScreeningModel.load(path)
        assert other.artifact==m.artifact
        assert other.new_trainer().protocol_id==m.new_trainer().protocol_id


def test_pid_model_does_not_compare_smiles_to_pid_hashes():
    pytest.importorskip("rdkit")
    model=load_pretrained("tg-high",warn=False)
    with pytest.raises(STCAError,match="PID groups"):
        model.evaluate_smiles(["*CC*","*CCO*"],[1.,2.])
