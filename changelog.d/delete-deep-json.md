### Fixed

- A DELETE request with a JSON body nested very deeply gets "The JSON is nested too deeply" (400)
  like the other requests, instead of a server error.
