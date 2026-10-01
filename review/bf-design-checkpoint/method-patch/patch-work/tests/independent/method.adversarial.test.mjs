import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {profile, validateProfile, methodInstructions, CURRENT_PROVIDER, PROFILES, capabilityAdmission, revisionRecord, digest} from '../../changed/pi-overlay/packages/bf-harness/src/method.ts';

const sha = text => crypto.createHash('sha256').update(text).digest('hex');
const baseline = '{"circuit":{"cin_uF":68}}\n';
const revised = '{"circuit":{"cin_uF":82}}\n';
const artifactDir=path.join(path.dirname(fileURLToPath(import.meta.url)),'artifacts');
fs.mkdirSync(artifactDir,{recursive:true});
fs.writeFileSync(path.join(artifactDir,'baseline-candidate.json'),baseline);
fs.writeFileSync(path.join(artifactDir,'revised-candidate.json'),revised);
const before = { 'candidate.json': sha(fs.readFileSync(path.join(artifactDir,'baseline-candidate.json'))) };
const after = { 'candidate.json': sha(fs.readFileSync(path.join(artifactDir,'revised-candidate.json'))) };
const makeInput = () => ({opportunity: 1, requested_kind:'parameter_refinement', observation_ids:['observed-baseline'], rationale:'Observed storage failure warrants testing a larger physical capacitor.', falsifier:'The same storage failure remains after substitution.'});
const makeContext = (id='strong_generic') => ({profile:profile(id),previous_artifacts:{...before},current_artifacts:{...after},observation_ids:['observed-baseline'],round:1,used_opportunities:[]});
const relation = () => ({id:'storage',function:'store',implementation:'physical capacitor',resource:'energy',condition:'observed baseline failure',artifact_ids:['candidate.json'],observation_ids:['observed-baseline']});

for (const id of ['strong_generic','bf_design','representation_only','revision_only']) {
  test(`profile ${id} has exactly two opportunities and valid semantics`, () => {
    const p=profile(id); assert.equal(p.candidate_opportunities,2); assert.deepEqual(validateProfile(p),p);
    const prompt=methodInstructions(p);
    assert.match(prompt,/same public requirements, facts, history, tools, baseline, feedback and validity checks/);
    assert.match(prompt,/exactly two candidate opportunities/);
    assert.match(prompt,/You may propose architecture and cross-domain changes/);
    assert.match(prompt,p.R?/R=1: Maintain method-state.json/:/R=0: Use ordinary notes/);
    assert.match(prompt,p.Q?/Q=1: Attribute the observed conflict/:/Q=0: Use normal feedback-driven search/);
    if (!p.Q) assert.match(prompt,/Architecture and cross-domain proposals remain allowed/);
  });
}
test('all four method prompts are semantically different',()=>assert.equal(new Set(Object.keys(PROFILES).map(id=>methodInstructions(profile(id)))).size,4));
test('unknown and inherited profile names are rejected',()=>{for(const id of ['typo','constructor','__proto__']) assert.throws(()=>profile(id),/UNKNOWN_METHOD_PROFILE/);});
test('profile R/Q/opportunity drift is rejected',()=>{for(const change of [{R:true},{Q:true},{candidate_opportunities:3},{extra:'claim'}]) assert.throws(()=>validateProfile({...profile('strong_generic'),...change}),/METHOD_PROFILE_DRIFT/);});
test('parameter-only admission remains unqualified and unauthorized',()=>{const a=capabilityAdmission({architecture:false,candidate_artifact_sources:false});assert.equal(a.capability_compatible,true);assert.equal(a.execution_authorized,false);assert.equal(a.scientific_qualified,false);assert.equal(a.provider.architecture,false);});
test('architecture claims fail provider admission',()=>{const a=capabilityAdmission({architecture:true,candidate_artifact_sources:false});assert.equal(a.capability_compatible,false);assert.deepEqual(a.blockers,['PROVIDER_ARCHITECTURE_NOT_IMPLEMENTED']);});
test('artifact-backed architecture claims fail all missing capabilities',()=>{const a=capabilityAdmission({architecture:true,candidate_artifact_sources:true});assert.equal(a.capability_compatible,false);assert.equal(a.blockers.length,2);assert.equal(a.execution_authorized,false);});
test('missing or nonboolean capability values fail closed',()=>{for(const required of [null,{}, {architecture:0,candidate_artifact_sources:false},{architecture:false,candidate_artifact_sources:'false'}]) assert.throws(()=>capabilityAdmission(required),/CAPABILITY_REQUIREMENTS_REQUIRED/);});
test('CURRENT_PROVIDER cannot be mutated to claim architecture',()=>assert.throws(()=>{CURRENT_PROVIDER.architecture=true},TypeError));
test('revision binds actual changed artifact hashes and existing observed IDs',()=>{const r=revisionRecord(makeInput(),makeContext());assert.deepEqual(r.before_artifacts,before);assert.deepEqual(r.after_artifacts,after);assert.deepEqual(r.changed_artifacts,['candidate.json']);assert.deepEqual(r.observation_ids,['observed-baseline']);assert.equal(r.implementation_status,'artifact_change_unverified');assert.equal(r.evaluation_status,'not_evaluated');assert.equal(r.acceptance_status,'not_accepted');assert.equal(r.execution_authorized,false);const {record_id,...body}=r;assert.equal(record_id,digest(body));});
test('architecture proposal plus parameter file change is never certified as architecture',()=>{const r=revisionRecord({...makeInput(),requested_kind:'architecture_recomposition'},makeContext());assert.equal(r.implementation_status,'proposed_unsupported');assert.equal(r.blocker,'PROVIDER_ARCHITECTURE_NOT_IMPLEMENTED');assert.equal(r.scientific_success,false);});
test('no-op revision is recorded honestly',()=>{const c=makeContext();c.current_artifacts={...c.previous_artifacts};const r=revisionRecord(makeInput(),c);assert.equal(r.implementation_status,'no_op');assert.deepEqual(r.changed_artifacts,[]);});
test('record rejects caller-manufactured evaluated status and changed hashes',()=>{for(const extra of [{evaluation_status:'evaluated'},{scientific_success:true},{before_artifacts:{evil:sha('evil')}}]) assert.throws(()=>revisionRecord({...makeInput(),...extra},makeContext()),/REVISION_FIELDS/);});
test('nonexistent and duplicate observations are rejected',()=>{for(const ids of [[],['invented'],['observed-baseline','observed-baseline']]) assert.throws(()=>revisionRecord({...makeInput(),observation_ids:ids},makeContext()),/REVISION_UNKNOWN_OBSERVATION/);});
test('consumed and excessive opportunities are rejected',()=>{for(const opportunity of [0,3,'1']) assert.throws(()=>revisionRecord({...makeInput(),opportunity},makeContext()),/REVISION_OPPORTUNITY_USED_OR_OUTSIDE_BUDGET/);const c=makeContext();c.used_opportunities=[1];assert.throws(()=>revisionRecord(makeInput(),c),/REVISION_OPPORTUNITY_USED_OR_OUTSIDE_BUDGET/);});
test('artifact hashes must be actual SHA-256 shape',()=>{const c=makeContext();c.current_artifacts={'candidate.json':'not-a-hash'};assert.throws(()=>revisionRecord(makeInput(),c),/ARTIFACT_HASH_REQUIRED/);});
test('representation requires relations and marks changed dependencies stale',()=>{assert.throws(()=>revisionRecord(makeInput(),makeContext('bf_design')),/METHOD_RELATIONS_REQUIRED/);const r=revisionRecord({...makeInput(),relations:[relation()]},makeContext('bf_design'));assert.equal(r.relations[0].support_status,'stale_after_revision');});
test('relations cannot reference invented artifacts or observations',()=>{for(const update of [{artifact_ids:['not-uploaded.c']},{observation_ids:['invented']}]) assert.throws(()=>revisionRecord({...makeInput(),relations:[{...relation(),...update}]},makeContext('bf_design')),/METHOD_RELATION_UNKNOWN/);});
test('retained unrelated relations do not gain evidence validation',()=>{const c=makeContext('bf_design');c.previous_artifacts['notes.md']=sha('unchanged');c.current_artifacts['notes.md']=sha('unchanged');const r=revisionRecord({...makeInput(),relations:[{...relation(),artifact_ids:['notes.md']}]},c);assert.equal(r.relations[0].support_status,'unknown_not_independently_validated');});

// Independent integrity probes: these tests express required fail-closed behavior.
test('unknown provider requirements must not silently pass admission',()=>{assert.throws(()=>capabilityAdmission({architecture:false,candidate_artifact_sources:false,firmware_source:true}));});
test('exported treatment definitions are deeply immutable',()=>{const old=PROFILES.bf_design.R;try {assert.throws(()=>{PROFILES.bf_design.R=false},TypeError);} finally {if (PROFILES.bf_design.R !== old) PROFILES.bf_design.R=old;}});
test('revision receipts must not alias mutable caller artifact manifests',()=>{const c=makeContext();const i=makeInput();const r=revisionRecord(i,c);c.current_artifacts['candidate.json']=sha('tampered after record');i.observation_ids.push('invented after record');const {record_id,...body}=r;assert.equal(record_id,digest(body));assert.deepEqual(r.after_artifacts,after);assert.deepEqual(r.observation_ids,['observed-baseline']);});
