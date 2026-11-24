### Changed

- The inventory's "VLAN or IP range" type is split into **VLAN** and **Prefix or range**. Existing
  entries move by themselves: those with a prefix become prefixes, and a VLAN they named gets its
  own entry. NetBox and discovery feed VLANs and prefixes separately.
- A firewall range is now a prefix with firewalls set: the plan is kept on the inventory's prefix,
  so a network is written down once. Planning a range for a network the inventory knows puts the
  plan on that prefix. Existing ranges move onto prefixes, with their group, tags and notes.

### Removed

- The separate "Firewall range" inventory type: firewall ranges are prefixes now.
