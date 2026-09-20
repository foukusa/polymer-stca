# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

import os
import subprocess
import sys
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest

from stca.cli import main
from stca import ScreeningModel


def test_cli_profiles(capsys):
    assert main(['profiles'])==0
    assert 'ec-low' in capsys.readouterr().out


def test_cli_generic_train_holdout_screen(tmp_path):
    rng=np.random.default_rng(23)
    X=rng.integers(0,2,(200,4))
    y=12*X[:,0]-8*X[:,1]+rng.normal(size=200)
    frame=pd.DataFrame(X,columns=['a','b','c','d'])
    frame['target']=y;frame['id']=[f'id{i}' for i in range(200)]
    frame['split']=['train']*150+['test']*50
    path=tmp_path/'training.csv';frame.to_csv(path,index=False)
    root=tmp_path/'runs'
    args=['train','--input',str(path),'--features','a,b,c,d','--target','target','--target-unit','arbitrary',
          '--tiers','.2','--scan-step','.25','--group-column','id','--split-column','split','--output-dir',str(root)]
    assert main(args)==0
    assert (root/'model.json').exists() and (root/'test_metrics.json').exists()
    m=ScreeningModel.load(root/'model.json')
    assert m.provenance['n_source_records']==150
    assert m.provenance['external_labels_used_for_fit'] is False
    assert main(args)==2 # no accidental overwrite
    out=tmp_path/'screen.csv'
    assert main(['screen','--input',str(path),'--features','a,b,c,d','--model',str(root/'model.json'),
                 '--tier','.2','--output',str(out)])==0
    screened=pd.read_csv(out)
    assert len(screened)==200 and 'id' in screened and 'selected' in screened


def test_cli_smiles_screen_invalid_report(tmp_path):
    pytest.importorskip('rdkit')
    path=tmp_path/'in.csv';out=tmp_path/'out.csv'
    pd.DataFrame({'id':[1,2,3],'SMILES':['CC','bad_smiles','*CC*']}).to_csv(path,index=False)
    with pytest.warns(UserWarning):
        assert main(['screen','--profile','tg-high','--tier','.1','--input',str(path),
                     '--output',str(out),'--errors','report'])==0
    result=pd.read_csv(out)
    assert len(result)==3 and pd.isna(result.loc[1,'selected'])


def test_cli_rejects_overlapping_groups(tmp_path):
    p=tmp_path/'x.csv'
    pd.DataFrame({'a':[0,1,0,1,0,1],'y':[1,5,2,6,3,7],
                  'g':['x','x','a','b','c','d'],'split':['train','test','train','train','test','test']}).to_csv(p,index=False)
    assert main(['train','--input',str(p),'--features','a','--target','y','--target-unit','u',
                 '--group-column','g','--split-column','split','--output-dir',str(tmp_path/'run')])==2
    assert not (tmp_path/'run'/'model.json').exists()


def test_cli_smiles_custom_training_with_synthetic_targets(tmp_path):
    pytest.importorskip('rdkit')
    from stca.chemistry import maccs_from_smiles
    smiles=['C','CC','CCC','CCCC','CCCCC','CCCCCC','CO','CCO','CCCO','CCCCO',
            'COC','CCOC','CN','CCN','CCCN','CCCCN','CNC','CCNC',
            'c1ccccc1','Cc1ccccc1','CCc1ccccc1','Oc1ccccc1','Nc1ccccc1','COc1ccccc1',
            'Clc1ccccc1','Fc1ccccc1','c1ccncc1','c1ccoc1','c1ccsc1','c1ccc2ccccc2c1']
    X,_=maccs_from_smiles(smiles)
    target=20*X[:,162].astype(float)-9*X[:,151]+np.arange(len(smiles))*.1
    test_rows={2,7,12,19,24,27}
    frame=pd.DataFrame({'SMILES':smiles,'synthetic_target':target,
                        'split':['test' if i in test_rows else 'train' for i in range(30)]})
    path=tmp_path/'synthetic_smiles.csv';frame.to_csv(path,index=False)
    root=tmp_path/'fit'
    assert main(['train','--input',str(path),'--target','synthetic_target',
                 '--target-name','SYNTHETIC','--target-unit','arbitrary',
                 '--tiers','.2','--scan-step','.25','--split-column','split',
                 '--output-dir',str(root)])==0
    model=ScreeningModel.load(root/'model.json')
    assert model.artifact['feature_spec']['kind']=='rdkit_maccs167'
    assert model.provenance['n_source_records']==24
    metrics=json.loads((root/'test_metrics.json').read_text())
    assert len(metrics)==1 and metrics[0]['n']==6
    assert metrics[0]['group_overlap_audit']=='disjoint'
