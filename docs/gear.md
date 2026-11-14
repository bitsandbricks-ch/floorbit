# Gear loans

`/gear` (from the incident board) shows who has which piece of gear right now: a spare switch lent
to a tech, or an access point out at the hall 2 stage. Issue #36.

**The gear itself is not kept in Floorbit.** The list is the [inventory](inventory.md), which NetBox
feeds through the NetBox plugin. Devices can also be added by hand. Floorbit keeps no stock or
quantities, because those live in NetBox. It only tracks loans.

- **Check out** a piece to a person (an account, or any name) or an area, with an optional note.
  A piece that is out has to be checked in before it can go to someone else.
- **Check in** brings it back. The history keeps how long it was out.
- **QR labels:** **Print QR labels** gives an A4 sheet, 4 × 8 labels, with the name, model and
  serial. Pick a kind first to print only that kind. The QR code opens `/gear?item=<id>`, so a
  phone scan goes straight to that piece's check-out or check-in. The link uses `PUBLIC_URL` when it
  is set.
- **Filters:** search by name, model, serial or who has it, by kind, and by what is out or here.

Loans and their history (the newest 2000 entries) are kept in `data.json` under `loans`. The
teardown checklist (#37) reads what is still out. Using the page needs **Work incidents** (techs,
leads, admins), because it names people. Every check-out and check-in goes to the audit log under
"gear", and shows up in the [shift handover](handover.md)'s changes.
