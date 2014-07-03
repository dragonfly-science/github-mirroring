GitHub mirroring
================

A simple python script to mirror all of an organization's GitHub repositories.

This script was designed to keep our local Gitolite server in sync with
repositories, but it will also let you just archive your GitHub repositories
locally. There is a more background in this [Medium post](https://medium.com/dragonfly-data-science/23002a10aefc).

Getting started
===============

To get started, clone the repository and run `python github-mirror.py -h` for usage information. The only additional dependency is [requests](http://docs.python-requests.org/en/latest/index.html).

1. `git clone https://github.com/dragonfly-science/github-mirroring.git` to get the code
2. `pip install requests` to install dependencies
3. `cd github-mirroring` change into the source directory (or copy the script where you like)
4. `python github-mirror.py -h` run with the help flag for usage information

In order for it to access the repositories, the GitHub access token for the account needs to be set as the environment variable `GITHUB_OAUTH_TOKEN`. 

Minimal examples
=================

### Backup up your public repositories to local storage

`python github-mirror.py yourname -a user --repository-type=public`

### Backup your organisation's private repositories to local storage

`GITHUB_OAUTH_TOKEN=becb84bde335a242707af71dae41a24f python github-mirror.py yourorganisation`

First, generate a GitHub Personal Access Token, by going to `Account settings > Applications` on [github.com](http://www.github.com). Hit the `Generate new token` button. The default permissions of `repo`, `public_repo`, and `user` are sufficient for the simple case. If you are using the webhooks, you will also need the `write:repo_hook` permission. Copy the generated key, a random string of characters like `becb84bde335a242707af71dae41a24f`. This key
will need to be in the environment variable `GITHUB_OAUTH_TOKEN` when the command is run. 


The usual warnings apply
========================

Some effort has been made to make the script work in a range of situations, however
it has only been ested in our specific usecase - mirroring an organisation's
private repositories to a local Gitolite mirror. We are all care, no responsibility. Please
make sure you understand what the script does before letting it loose.
