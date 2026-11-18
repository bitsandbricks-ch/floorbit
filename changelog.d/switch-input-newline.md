### Security

- A switch username or port name with a newline at its end is refused instead of being sent to the
  switch. A show template can no longer chain commands with `;`, which NX-OS runs one after the
  other ("show clock ; reload").
