# Switch areas

**Seats > Switch areas** (`/switch-areas`) lists every switch in the inventory with the seats it
serves and where that comes from. Floorbit uses it when a check-in has to ask the switches for a PC
([segments](segments.md)): the seat's own switches are asked first.

## Where a switch's seats come from

Strongest first:

1. **Pinned.** Pin a switch to blocks, rows or single seats, or leave it out (for distribution and
   core switches). A pin wins over everything else.
2. **Learned.** A seat mapped to one of the switch's ports puts that seat on the switch: from the
   [seat walk-through](seat-walk.md), a check-in, or a cable in the patch plan ([cables](cables.md)).
3. **Drawn in a block.** A switch drawn inside a block's area on the floor plan, the aisles between
   its rows included, serves the whole block. A switch outside every block is not guessed: it is a
   **to-do** until it is pinned, drawn in its block, or its seats are walked.

A switch can serve several blocks and rows.

The crew works a row at a time, so rows are the finer unit. When every seat of a row is learned on
one switch, the page offers **Pin row ...**: one click and the row is pinned.

## When the sources disagree

The page shows the disagreement and leaves the decision to the crew:

- seats learned on a switch outside its pin;
- seats learned outside the block the switch is drawn in;
- a switch drawn in one block but pinned to another;
- a switch that is left out but has seats learned on it.

The page names the switches with a to-do or a disagreement at the top.

The seat walk says it where it is found, too: when a seat's port turns up on a switch pinned to
another row ("sw-a-02 is pinned to A 1; this seat is in A 2"), drawn in another block, or left
out, the result card says so with a link here, so the walker fixes the pin or the patch on the spot.

Who may: reading needs `seats.view`, pinning `seats.edit`. Pins are kept per event, and every
change is in the audit log.
