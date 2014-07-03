Github mirroring
================

Simple python script to mirror all of an organization's github repositories.
The only additional dependency is [requests](http://docs.python-requests.org/en/latest/index.html)


This script was designed to keep our local gitolite server in sync with
repositories, but it will also let you just archive your github repositories
locally.

See this medium post for details -

Every effort has been made to make the script work in a range of situations, however
it has only been rigoursly tested in our specific usecase - mirroring an organisation's
private repositories to a local gitolite mirror.
