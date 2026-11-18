### Security

- The LibreNMS token no longer follows a redirect. It travels in a header of its own, which a redirect
  to another host (even plain http) took along, so the token could reach a server other than the one
  it is saved with. Floorbit now says where LibreNMS redirects to, in the connection test too.
