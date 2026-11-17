### Security

- A custom "show" switch command template can't write its output to a file on the switch
  (`| redirect`, `| append`, `| tee`, `| save`): techs may run show templates, and those pipes write.
  Such a command has to be a change template.
