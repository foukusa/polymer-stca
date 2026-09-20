# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-Peer-Review
# See LICENSE for academic peer review and permission requirements.

"""Optional parity check against TRUSTED original local STCA code and CSV files.

This executes the explicitly supplied Python core. Do not point it at untrusted
code. It compares the scan, ranked key lists and cumulative-prefix masks, not
whole-manuscript benchmarks or source-versus-external selection protocols.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

import numpy as np

from stca import ScanConfig, scan_frequencies, signed_rankings, signed_prefix_rules, load_legacy_pair
from stca.model import dump_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--property',choices=['tg','ec'],required=True)
    p.add_argument('--core',required=True,help='Trusted original thermal/electrical core Python file.')
    p.add_argument('--fingerprints',required=True);p.add_argument('--targets',required=True)
    p.add_argument('--has-header',action='store_true')
    p.add_argument('--layout',choices=['maccs167','maccs166_keys1to166'],default='maccs167')
    p.add_argument('--scan-step',type=float,required=True,help='Use the exact archived setting.')
    p.add_argument('--min-subset-size',type=int,default=1)
    p.add_argument('--max-rank',type=int,default=10)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    core_path=Path(args.core).resolve()
    spec=importlib.util.spec_from_file_location('_stca_explicit_trusted_reference_core',core_path)
    if spec is None or spec.loader is None: raise RuntimeError('Cannot load supplied trusted core.')
    core=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=core
    spec.loader.exec_module(core)
    X,y,_=load_legacy_pair(args.fingerprints,args.targets,has_header=args.has_header,layout=args.layout)
    direction='high' if args.property=='tg' else 'low'
    cfg=ScanConfig(step=args.scan_step,min_subset_size=args.min_subset_size,
                   max_points=getattr(core,'STCA_MAX_SCAN_POINTS',2_000_000),
                   nominal_alpha=getattr(core,'STCA_NOMINAL_P_CUTOFF',.05))
    old=(core.stca_correlation_table(X,y,direction,args.scan_step,args.min_subset_size)
         if args.property=='tg' else
         core.stca_correlation_table(X,y,direction,'value',args.scan_step,args.min_subset_size))
    new=scan_frequencies(X,y,direction=direction,config=cfg)
    np.testing.assert_allclose(new.thresholds,old[1],rtol=1e-12,atol=1e-12)
    np.testing.assert_allclose(new.frequencies,old[2],rtol=1e-12,atol=1e-12)
    a=new.table.set_index('key').sort_index()
    b=old[0].set_index('key').sort_index()
    assert a.index.tolist()==b.index.tolist(),'Nonconstant key set differs.'
    for col in ('correlation','nominal_p_value','feature_prevalence'):
        np.testing.assert_allclose(a[col],b[col],rtol=1e-9,atol=1e-12)
    pos,neg,_=signed_rankings(new,cfg)
    old_pos,old_neg=core.stca_rankings_from_table(old[0],'STCA')
    assert pos==old_pos.key.astype(int).tolist(),'Positive ranking differs.'
    assert neg==old_neg.key.astype(int).tolist(),'Negative ranking differs.'
    new_rules=signed_prefix_rules(pos,neg,args.max_rank)
    old_rules=core.make_signed_prefix_patterns('STCA',old_pos,old_neg,args.max_rank)
    old_by_name={r.name:r for r in old_rules}
    assert len(new_rules)==len(old_rules),'Candidate count differs.'
    for rule in new_rules:
        previous=old_by_name[rule.name]
        reference=np.ones(len(X),dtype=bool)
        for k,v in zip(previous.keys,previous.values): reference &= X[:,int(k)]==int(v)
        np.testing.assert_array_equal(rule.apply(X),reference)
    dump_json(args.output,{'status':'PASS','scope':'source_scan_rankings_prefix_masks_only',
                           'source_core_filename':core_path.name,'n_records':len(X),
                           'candidate_masks_compared':len(new_rules),'whole_paper_reproduction':False})
    print(f'PASS: {len(new_rules)} source candidate masks and scan/rankings. Not a full manuscript audit.')


if __name__=='__main__': main()
