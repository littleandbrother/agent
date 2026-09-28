export type Digest = `sha256:${string}`

export interface RunRef {
  schema_version: 'bfworld-run-ref-v1'
  run_id: string
  bundle_digest: Digest
  event_head: Digest
}

export interface PublicObservation {
  schema_version: 'bfworld-public-observation-v1'
  run_id: string
  event_head: Digest
  baseline_passed: boolean
  revised_passed: boolean
  fine_validation_passed: boolean
  claim_boundary: string
}
