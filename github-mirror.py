'''
Mirrors repositories from github.com
'''
from __future__ import print_function
import argparse
import requests
import json
import sys
import shlex
import re
from os.path import join, exists, isdir
from os import environ, mkdir
from subprocess import Popen, PIPE
from threading import Thread
from Queue import Queue
from itertools import izip_longest

TOKEN = environ[
    'GITHUB_OAUTH_TOKEN'] if 'GITHUB_OAUTH_TOKEN' in environ else None
GITLAB_API_TOKEN = environ[
    'GITLAB_API_TOKEN'] if 'GITLAB_API_TOKEN' in environ else None

class MirrorError(RuntimeError):
    pass


# http://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks-in-python
def grouper(n, iterable, padvalue=None):
    "grouper(3, 'abcdefg', 'x') --> ('a','b','c'), ('d','e','f'), ('g','x','x')"
    return izip_longest(*[iter(iterable)] * n, fillvalue=padvalue)


def gitcmd(args, cwd, msg, quiet=False):
    cmd = shlex.split('git %s' % args)
    p = Popen(cmd, cwd=cwd, stdout=PIPE, stderr=PIPE)
    if not quiet:
        print('INFO: %s' % msg)
    p.wait()
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        raise MirrorError('%s failed with error\n\t%s' % (msg, stderr))


def getargs():
    'Get command line arguments'
    parser = argparse.ArgumentParser(
        description='''Mirror repositories from github.com

                       It is possible to specify a combination of entity,
                       github-access, and repository-type that not valid. If you
                       are having trouble check
                       https://developer.github.com/v3/repos/#list-your-repositories
                    ''')
    parser.add_argument('entity',
                        help='github.com entity (organisation or user) to mirror')
    parser.add_argument('--repo',
                        help='github.com repo to mirror')
    parser.add_argument('--mirror-host', '-m',
                        help='host to mirror to')
    parser.add_argument('--mirror-type', '-t',
                        default='gitolite',
                        choices=['gitolite', 'gitlab'],
                        help='mirror type [gitolite]')
    parser.add_argument('--repository-type', '-r',
                        choices=['private', 'public', 'all', 'owner'],
                        default='private',
                        help='type of repositories to mirror [private]')
    parser.add_argument('--working-directory', '-d',
                        default='.',
                        help='directory to use [.]')
    parser.add_argument('--repo-directory',
                        default='repos',
                        help='directory to store repositories locally')
    parser.add_argument('--webhook-url',
                        help='url for github webhook notifications')
    parser.add_argument('--webhook-content-type',
                        default='form',
                        help='content type for github webhook, [form]')
    parser.add_argument('--webhook-events',
                        default='push',
                        nargs='+',
                        help='events to trigger github webhooks on [push]')
    parser.add_argument('--github-access', '-a',
                        choices=['org', 'user'],
                        default='org',
                        help='Access user or organisation repositories [org]')
    parser.add_argument('--quiet', '-q',
                        action='store_true',
                        help="run with minimal messages")
    parser.add_argument('--max-threads',
                        default=8,
                        type=int,
                        help='maximum number of job threads')
    parser.add_argument('--num-repos',
                        default=1000,
                        type=int,
                        help='number of repositories to mirror (max 1000)')

    return parser.parse_args()


def repo_dir(args):
    return join(args.working_directory, args.repo_directory)


def setup(args):
    'Check that the environment has been configured'
    if not isdir(args.working_directory):
        raise MirrorError(
            'Working directory %s does not exist' % args.working_directory)
    if args.mirror_host:
        if args.mirror_type == 'gitolite':
            admin_dir = join(args.working_directory, 'gitolite-admin')
            if not isdir(admin_dir):
                if exists(admin_dir):
                    raise MirrorError('gitolite-admin cannot be a file')
                gitcmd(
                    'clone %s:gitolite-admin' % args.mirror_host,
                    args.working_directory,
                    'Cloning gitolite admin repository',
                    args.quiet)

    if not isdir(repo_dir(args)):
        try:
            mkdir(repo_dir(args))
        except OSError:
            raise MirrorError('could not create directory %s' % repo_dir(args))


def get_github_repositories(args):
    'Checks to see if there are any new repositories'
    # if you have more than 1000 repoes this won't work ...
    payload = {'per_page': args.num_repos, 'type': args.repository_type}
    if args.repository_type in ('private', 'all'):
        if not TOKEN:
            raise MirrorError(
                'The environment vairable GITHUB_OAUTH_TOKEN must be set to access private repositories')
        payload['access_token'] = TOKEN
    if args.github_access != 'user':
        target = 'orgs/%s' % args.entity
    else:
        if TOKEN:
            target = 'user'
        else:
            target = 'users/%s' % args.entity
    url = 'https://api.github.com/%s/repos' % target
    req = requests.get(url, params=payload)
    if req.status_code != 200:
        raise MirrorError('Getting list of repositories failed')
    return json.loads(req.content)


def create_new_gitolite_repo(name, args):
    'Creates a new repository on code.dragonfly.co.nz'
    gitolite_repo = '%s:%s' % (args.mirror_host, name)
    try:
        gitcmd('ls-remote %s' % gitolite_repo,
               args.working_directory,
               'Checking to see if %s exists on %s' % (
                   name, args.mirror_host)
               )
    except MirrorError:
        admin_dir = join(args.working_directory, 'gitolite-admin')
        gitcmd('pull origin master',
               admin_dir,
               'Pulling most recent gitolite admin',
               True)
        with open(join(admin_dir, 'conf', 'gitolite.conf'), 'r+') as conf:
            conf.seek(-1, 2)
            if conf.read() != '\n':
                conf.write('\n')
            conf.seek(0, 2)
            name = re.sub('.git$', '', name)
            conf.write('\nrepo    %s\n    RW+  = @dragonfly\n' % name)
        gitcmd('add conf/gitolite.conf',
               admin_dir,
               'Updating gitolite config file',
               True)
        gitcmd('commit -m "added %s"' % name,
               admin_dir,
               'Updating gitolite config file',
               args.quiet)
        gitcmd('push origin master',
               admin_dir,
               'Pushing updated gitolite config',
               True)

def create_new_repo(name, args):
    if args.mirror_type == 'gitlab':
        args.gitlab.create_project(name)
    elif args.mirror_type == 'gitolite':
        create_new_gitolite_repo(name + '.git', args)
        if args.wiki_url:
            create_new_gitolite_repo(name + '.wiki.git', args)
    else:
        raise MirrorError('Unknown repo type')

def get_remote_url(args, name):
    if args.mirror_type == "gitolite":
        return '%s:%s' % (args.mirror_host, name + '.git')
    if args.mirror_type == "gitlab":
        return '%s:%s/%s' % (args.mirror_host, args.entity, name + '.git')

def update_mirror(repo, args):
    name = repo['name']

    remote_url = get_remote_url(args, name)
    wdir = join(repo_dir(args), name + '.git')
    git_push(remote_url, wdir, name, args)

    if args.wiki_url is None:
        return

    remote_url = get_remote_url(args, name + '.wiki')
    wikidir = join(repo_dir(args), name + '.wiki.git')
    git_push(remote_url, wikidir, name + ' wiki', args)

def install_webhook(repo, args):
    if not TOKEN:
        raise MirrorError(
            'Set GITHUB_OAUTH_TOKEN environment variable to add a webhook')
    api_url = repo['hooks_url']

    # See if the hook has already been installed
    req = requests.get(api_url, params={'access_token': TOKEN})
    if req.status_code != 200:
        raise MirrorError('Problem fetching hook list')
    hooks = filter(
        lambda x: 'url' in x['config'] and x[
            'config']['url'] == args.webhook_url,
        json.loads(req.content)
    )
    if len(hooks) == 0:
        hook_data = {
            "name": "web",
            "active": True,
            "events": args.webhook_events,
            "config": {
                "url": args.webhook_url,
                "content_type": args.webhook_content_type
            }
        }
        req = requests.post(
            api_url, params={'access_token': TOKEN}, data=json.dumps(hook_data))
        if req.status_code != 201:
            raise MirrorError('Webhook installation failed')


def get_github_wiki_url(url, name, args):
    wiki_url = re.sub('.git$', '.wiki.git', url)
    try:
        gitcmd('ls-remote %s' % wiki_url, '.', 'Checking for %s wiki' % name, True)
        print('INFO: Found wiki for %s' % name)
    except MirrorError:
        return None
    return wiki_url

def get_clone_url(repo, args):
    # add token to clone url
    clone_url = repo['clone_url']
    if TOKEN and args.repository_type != 'public':
        clone_url = clone_url.replace('https://', 'https://%s@' % TOKEN)
    return clone_url

def git_fetch(dir, name, args):
    gitcmd(
        'fetch -p origin', dir,
        'Fetching latest version of %s from github' % name, args.quiet)

def git_clone(url, dir, name, args):
    gitcmd(
        'clone --mirror %s' % url, dir,
        'Mirror cloning %s from github.com' % name, args.quiet)

def git_push(url, dir, name, args):
    gitcmd(
        'push --mirror %s' % url, dir,
        'Pushing latest version of %s from local folder to %s' % (name, args.mirror_host),
        args.quiet)

def update_local(repo, args):
    clone_url = get_clone_url(repo, args)
    base_dir = repo_dir(args)
    wdir = join(base_dir, repo['name'] + '.git')
    if exists(wdir):
        git_fetch(wdir, repo['full_name'], args)
    else:
        git_clone(clone_url, base_dir, repo['full_name'], args)

    args.wiki_url = get_github_wiki_url(clone_url, repo['name'], args)
    if not args.wiki_url:
        return

    wikidir = join(base_dir, repo['name'] + '.wiki.git')
    if exists(wikidir):
        git_fetch(wikidir, repo['full_name'] + ' wiki', args)
    else:
        git_clone(args.wiki_url, base_dir, repo['full_name'] + ' wiki', args)

def mirror_repo(repo, args, msgs):
    try:
        update_local(repo, args)

        if args.webhook_url:
            install_webhook(repo, args)

        if args.mirror_host:
            create_new_repo(repo['name'], args)
            update_mirror(repo, args)

    except MirrorError as e:
        msgs.put(e.message)

class GitlabHost(object):

    def __init__(self, args):
        self.args = args
        self.host = args.mirror_host.replace("git@", "")
        self.api_base = "https://%s/api/v4" % self.host
        self.namespace_id = self.get_namespace_id()
        self.projects = self.api_get("/projects")

    def api_get(self, url):
        auth_url = self.api_base + url + "?private_token=%s" % GITLAB_API_TOKEN
        response = requests.get(auth_url)
        if response.status_code not in (200, 201):
            print("API request failed (%s), status %d" % (url, response.status_code))
            return {}
        return json.loads(response.content)

    def api_post(self, url, data):
        auth_url = self.api_base + url + "?private_token=%s" % GITLAB_API_TOKEN
        response = requests.post(auth_url, data)
        if response.status_code not in (200, 201):
            print("API request failed (%s), status %d" % (url, response.status_code))
            return {}
        return json.loads(response.content)

    def get_namespace_id(self):
        namespaces = self.api_get("/namespaces")
        for ns in namespaces:
            if ns['name'] == self.args.entity:
                return ns['id']
        return

    def get_project(self, name):
        for p in self.projects:
            if p['name'] == name:
                return p

    def create_project(self, name):
        if not self.get_project(name):
            self.api_post("/projects", dict(name=name, namespace_id=self.namespace_id))

if __name__ == '__main__':
    try:
        args = getargs()
        setup(args)
        repos = get_github_repositories(args)
        msgs = Queue()
        if args.repo:
            repos = filter(lambda x: x['name'] == args.repo, repos)
            if len(repos) < 1:
                print("WARN: Repo %s not found in github" % args.repo)

        if args.mirror_host and args.mirror_type == "gitlab":
            args.gitlab = GitlabHost(args)

        # split list of repos into groups to limit the number of threads
        repo_sets = grouper(args.max_threads, repos)
        for repo_set in repo_sets:
            tp = [Thread(target=mirror_repo, args=(repo, args, msgs))
                  for repo in repo_set if repo]
            map(lambda t: t.start(), tp)
            map(lambda t: t.join(), tp)

        problems = []
        while not msgs.empty():
            problems.append(msgs.get_nowait())
        if len(problems) != 0:
            raise MirrorError('\n\t'.join(problems))

    except MirrorError as e:
        print("ERROR:", e, file=sys.stderr)
        exit(1)
    exit(0)
