# ansible-nfsexport
Ansible module to add and remove NFS export entries


| Argument | Required | Default | Choices | Description |
| --- | --- | --- | --- | --- |
| name | yes | | | Descriptive text to be returned |
| action | yes | | <ul><li>add</li><li>remove</li></ul> | Select operation to perform |
| update | no | true | <ul><li>True</li><li>False</li></ul> | Should the system be updated when this command finishes |
| clear_all | no | false | <ul><li>True</li><li>False</li></ul> | Discard all existing exports before performing this operation |
| path | yes | |  | The path to export. Must already exist on the system |
| clients | yes | | <ul><li>*</li><li>hostname</li><li>IP address</li><li>x.x.x.x/n</li><li>*.example.com</li><li>@nisgroup</li></ul> | The client(s) that matches this rule |
| read_only | no | true | <ul><li>True</li><li>False</li></ul> | Is this export read-only or read-write |
| root_squash | no | true | <ul><li>True</li><li>False</li></ul> | Map request from uid/gid 0 to the anonymous uid/gid |
| al_squash | no | false | <ul><li>True</li><li>False</li></ul> | Map all requests to the anonymous uid/gid |
| security | no | sys | <ul><li>sys (No security)</li><li>krb5 (kerberos authentication)</li><li>krb5i (krb5 + integrity protection)</li></li>krb5p (krb5i + privacy protection)</li></ul> | Colon delimited list of security flaours to negotiate |
| options | no | | See exports(5) | Any additional options not otherwise listed |


Return values

| Value | Type | Content |
| --- | --- | --- |
| name | string | The text supplied in the `name` input argument |
| message | string | The output message |
| error | string | Detailed error description if any occur |
