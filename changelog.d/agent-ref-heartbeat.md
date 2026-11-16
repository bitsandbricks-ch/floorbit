### Added

- The Local agents page shows what each agent says about itself: how long it has been up, reconnects, syslog lines relayed and dropped, flow packets and calls turned away as busy. Agents send this over the link or `POST /api/agent/v1/report`; a report older than three minutes is not shown.
