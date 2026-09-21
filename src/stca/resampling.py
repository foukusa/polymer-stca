# Copyright (c) 2025, The University of Tokyo, University College London
# SPDX-License-Identifier: LicenseRef-STCA-Academic-NonCommercial
"""Explicit fixed-membership record-level full-discovery resampling.

This is not a canonical-grouped split experiment or a recreation of unseen SI
random seeds. Every replicate reruns discovery and the declared selection rule.
Invalid replicates are recorded, never replaced by zero or silently dropped.
"""
from __future__ import annotations
from dataclasses import replace
import numpy as np
import pandas as pd
from .errors import STCAError, NoValidRuleError
from .metrics import target_cutoff, labels_at, screening_metrics, strict_harmonic
from .model import tier_key
from .protocols import SelectionData


def frozen_core_statistics(model, source, comparison):
    """Report core H for the already selected rule; never select another rule here."""
    X,y=source;E,z=comparison
    rows=[]
    for tier in model.tiers:
        try:
            rule=model.rule_for(tier)
        except NoValidRuleError:
            rows.append({'tier':tier,'statistic':None,'status':'NO_VALID_SELECTED_RULE'})
            continue
        scores=[];flags=[]
        for a,b in ((X,y),(E,z),(np.vstack([X,E]),np.concatenate([y,z]))):
            cutoff=target_cutoff(b,tier,model.artifact['direction'])
            m=screening_metrics(labels_at(b,cutoff,model.artifact['direction']),rule.apply(a),
                                mcc_mode=model.artifact['mcc_mode'],
                                min_support=model.artifact['min_selected_support'])
            scores.append(m['average_score']);flags.append(m['valid_screen'])
        score=strict_harmonic(scores,flags)
        rows.append({'tier':tier,'statistic':score,'signature':rule.signature,
                     'status':'VALID' if score is not None else 'INVALID_CORE_COMPONENT'})
    return rows


def full_pipeline_resampling(trainer, source, comparison, *, kind, repeats, seed,
                             feature_names, feature_spec):
    """Bootstrap or permute each original split independently, then refit STCA.

    Raw observation resampling is declared. It must not be presented as grouped
    bootstrap when records share canonical structures or literature sources.
    No group identities are manufactured for bootstrap copies.
    """
    if kind not in ('bootstrap','permutation'):
        raise STCAError('kind must be bootstrap or permutation.')
    if isinstance(repeats,bool) or not isinstance(repeats,int) or repeats<1:
        raise STCAError('repeats must be a positive integer.')
    X,y=(np.asarray(v) for v in source); E,z=(np.asarray(v) for v in comparison)
    rng=np.random.default_rng(seed)
    def run(a,b,c,d):
        fresh=replace(trainer)
        kwargs={}
        if fresh.selection!='source_as':
            kwargs={'selection_data':SelectionData(c,d),'acknowledge_selection_labels':True}
        model=fresh.fit(a,b,feature_names_=feature_names,feature_spec=feature_spec,**kwargs)
        return frozen_core_statistics(model,(a,b),(c,d))
    observed=run(X,y,E,z)
    records=[]
    for i in range(repeats):
        if kind=='permutation':
            a,b,c,d=X,rng.permutation(y),E,rng.permutation(z)
        else:
            ix=rng.integers(0,len(y),len(y)); ie=rng.integers(0,len(z),len(z))
            a,b,c,d=X[ix],y[ix],E[ie],z[ie]
        try:
            result=run(a,b,c,d)
        except STCAError as exc:
            result=[{'tier':t,'statistic':None,'status':'FIT_FAILED','reason':str(exc)} for t in trainer.tiers]
        records.extend({'replicate':i,'kind':kind,'protocol_id':trainer.protocol_id,**r} for r in result)
    table=pd.DataFrame(records); summaries=[]
    for obs in observed:
        vals=table.loc[table.tier.eq(obs['tier']),'statistic'].to_numpy(dtype=float)
        finite=vals[np.isfinite(vals)]
        row={'tier':obs['tier'],'observed':obs['statistic'],'repeats':repeats,
             'valid_repeats':len(finite),'invalid_repeats':repeats-len(finite),
             'valid_fraction':len(finite)/repeats,'kind':kind,'seed':seed,
             'protocol_id':trainer.protocol_id,'sampling_unit':'records_within_fixed_split',
             'grouped_structure_bootstrap':False,'statistic':'core_harmonic_of_selected_rule',
             'selection_scope':trainer.selection,'exact_historical_rng_reproduction':False}
        if kind=='bootstrap':
            row.update(conditional_q025=float(np.quantile(finite,.025)) if len(finite) else None,
                       conditional_q975=float(np.quantile(finite,.975)) if len(finite) else None,
                       interval_status='CONDITIONAL_VALID_REPLICATES_ONLY' if len(finite) else 'NO_VALID_REPLICATES')
        else:
            valid_obs=obs['statistic'] is not None
            exceed=int(np.sum(finite>=obs['statistic'])) if valid_obs else None
            row.update(conditional_valid_null_p=(1+exceed)/(1+len(finite)) if valid_obs and len(finite) else None,
                p_lower_bound=(1+exceed)/(1+repeats) if valid_obs else None,
                p_upper_bound=(1+exceed+repeats-len(finite))/(1+repeats) if valid_obs else None,
                null_q95=float(np.quantile(finite,.95)) if len(finite) else None,
                permutation_status='CONDITIONAL_VALID_NULL' if valid_obs and len(finite) else 'NOT_ESTIMABLE')
        summaries.append(row)
    return table,pd.DataFrame(summaries)
