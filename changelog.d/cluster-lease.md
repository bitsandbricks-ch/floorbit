### Fixed

- Several pods: renewing the leader lease could overwrite a lease another pod had just taken, so two
  pods led for a moment and an alert could go out twice. A renewal now only lengthens the pod's own
  lease. Rows and calls from a pod running another version are skipped instead of stopping the
  agent list or a call worker.
