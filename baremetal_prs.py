#!/usr/bin/env python3

"""
Taking the PRs specified in the JSON file, evaluate a complexity score
associated with sideporting the PR into development.
"""

import argparse
import os
import json
import subprocess

class PullRequest:
    '''Class for storing information/metrics for a single PR'''
    def __init__(self, pr_dict, repo_name):
        if repo_name != 'mbedtls' and repo_name != 'mbedtls-restricted':
            raise ValueError("repo_name can only be 'mbedtls' or \
                              'mbedtls-restricted' ")
        self.repo_name = repo_name # mbedtls or mbedtls-restrictedfrom colorama import Fore
        self.bytes_saved = int(pr_dict['Bytes saved'])
        self.number = pr_dict['main PR'][1:]
        self.group = pr_dict['group']
        self.description = pr_dict['short description']
        self.score = None

    def get_metrics(self):
        '''Get and store various metrics for the PR through the GitHub CLI (gh):

        Metrics:
        * Number of commits
        * Number of files changed
        * Which files have been changed
        * Number of lines changed (additions + deletions)
        * The combined size of the changes (additions + deletions) for the
          changed files between the head of the PR and development
        '''
        # Checkout the PR
        cmd = f'gh pr checkout {self.number}'
        ret = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL,
                             stderr=subprocess.STDOUT)
        if ret != 0:
            msg = f'Could not checkout PR {self.number}.'
            subprocess.CalledProcessError(ret, cmd, output=msg)

        # Gather the PR metrics and store the JSON as a dictionary
        cmd = 'gh pr view --json changedFiles,files,commits,additions,deletions'
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        metrics_json_str = process.communicate()[0]
        try:
            metrics = json.loads(metrics_json_str)
        except:
            print(metrics_json_str)
            exit()


        self.commits_count = len(metrics['commits'])
        self.files_count = metrics['changedFiles']
        self.lines_changed = metrics['additions'] + metrics['deletions']
        self.files = []
        for f in metrics['files']:
            if f['path'].startswith('ChangeLog'):
                continue
            else:
                self.files.append(f['path'])

        if self.repo_name == 'mbedtls':
            dev_branch = 'development'
        else:
            dev_branch = 'development-restricted'

        total_add = 0
        total_del = 0
        for f in self.files:
            cmd = f'git diff --shortstat HEAD..{dev_branch} -- {f}'
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
            diff = ((process.communicate()[0]).decode('UTF-8')).split(',')
            if process.returncode != 0:
                msg = f'Could not get diff for HEAD..{self.repo_name} for \
                      PR {self.number}'
                print(msg)
                raise subprocess.CalledProcessError(process.returncode, cmd, msg)
            for s in diff:
                if s == '':
                    number = 0
                else:
                    number = int(''.join(i for i in s.strip() if i.isdigit()))
                if s.endswith('(+)'):
                    total_add += number
                if s.endswith('(-)'):
                    total_del += number

        self.dev_diff = total_add + total_del

class PullRequestGetter:
    '''Tools to checkout all specified PRs and get their metrics'''
    def __init__(self, json_path, mbedtls_path, restricted_path):
        # Convert possibly relative paths to absolute paths and store them
        self.mbedtls_path = os.path.abspath(mbedtls_path)
        self.restricted_path = os.path.abspath(restricted_path)

        # Make sure mbedtls/development is up-to-date
        subprocess.run('git checkout development; git pull',
                       cwd=self.mbedtls_path, shell=True)
        # Make sure mbedtls-restricted/development-restricted is up-to-date
        subprocess.run('git checkout development-restricted; git pull',
                       cwd=self.restricted_path, shell=True)

        # Extract PR numbers from the JSON file
        self.mbedtls_pulls = []
        self.restricted_pulls = []
        with open(json_path) as json_file:
            pulls = json.load(json_file)
            for pr in pulls:
                pr_number = pr['main PR']
                if pr_number.startswith('#'):
                    pr_object = PullRequest(pr,'mbedtls')
                    self.mbedtls_pulls.append(pr_object)
                elif pr_number.startswith('r'):
                    pr_object = PullRequest(pr,'mbedtls-restricted')
                    self.restricted_pulls.append(pr_object)
                else:
                    msg = f"PR Numbers should start with:\n \
                            '\#' for PRs from the mbedtls repository\n \
                            'r' for PRs from the mbedtls-restricted \
                            repository\n {pr_number} begins with neither."
                    raise ValueError(msg)

    def print_pulls(self):
        print("Public PRs:")
        for pr in self.mbedtls_pulls:
            print(f'PR: {pr.number}, Commits: {pr.commits_count}, Diff: {pr.dev_diff}, Files: {pr.files_count}')
        print("Restricted PRs:")
        for pr in self.restricted_pulls:
            print(f'PR: {pr.number}, Commits: {pr.commits_count}, Diff: {pr.dev_diff}, Files: {pr.files_count}')

        print(f'Max Commits: {self.max_commits}, Max Diff: {self.max_dev_diff}, Max Files: {self.max_files_count}')

    def get_metrics_by_repo(self, repo_name):
        if repo_name == 'mbedtls':
            repo_path = self.mbedtls_path
            repo_pulls = self.mbedtls_pulls
        elif repo_name == 'mbedtls-restricted':
            repo_path = self.restricted_path
            repo_pulls = self.restricted_pulls
        os.chdir(repo_path)
        for pr in repo_pulls:
            text = f'{pr.repo_name}/{pr.number}'
            spacing = '.' * (40- len(text))
            print(f'{text} {spacing} ', end='')
            pr.get_metrics()

            if pr.commits_count > self.max_commits:
                self.max_commits = pr.commits_count
            if pr.files_count > self.max_files_count:
                self.max_files_count = pr.files_count
            if pr.lines_changed > self.max_lines_changed:
                self.max_lines_changed = pr.lines_changed
            if pr.dev_diff > self.max_dev_diff:
                self.max_dev_diff = pr.dev_diff
            if pr.bytes_saved > self.max_bytes_saved:
                self.max_bytes_saved = pr.bytes_saved

            print('DONE')

    def get_metrics(self):
        '''Get metrics for all PRs'''
        self.max_commits = 0
        self.max_files_count = 0
        self.max_lines_changed = 0
        self.max_dev_diff = 0
        self.max_bytes_saved = 0

        print('Calculating metrics for all specified PRs...')
        # Get current working directory so we can come back to it
        cwd = os.getcwd()

        # Get metrics for public PRs
        self.get_metrics_by_repo('mbedtls')

        # Get metrics for restricted PRs
        self.get_metrics_by_repo('mbedtls-restricted')

        # Go back to old cwd
        os.chdir(cwd)

    def normalise_metric(self, pr_val, max_val):
        return (pr_val / max_val) * 100

    def normalise_metrics(self):
        for pr in (self.mbedtls_pulls + self.restricted_pulls):
            norm_metrics = {}
            norm_metrics['commits'] = self.normalise_metric(pr.commits_count, self.max_commits)
            norm_metrics['files_count'] = self.normalise_metric(pr.files_count, self.max_files_count)
            norm_metrics['lines_changed'] = self.normalise_metric(pr.lines_changed, self.max_lines_changed)
            norm_metrics['dev_diff'] = self.normalise_metric(pr.dev_diff, self.max_dev_diff)
            norm_metrics['bytes_saved'] = self.normalise_metric(pr.bytes_saved, self.max_bytes_saved)
            pr.score = calculate_score(norm_metrics)

    def print_pulls(self):
        print("Public PRs:")
        for pr in self.mbedtls_pulls:
            print(f'PR: {pr.number}, Commits: {pr.commits_count}, Diff: {pr.dev_diff}, Files: {pr.files_count}')
        print("Restricted PRs:")
        for pr in self.restricted_pulls:
            print(f'PR: {pr.number}, Commits: {pr.commits_count}, Diff: {pr.dev_diff}, Files: {pr.files_count}')

        print(f'Max Commits: {self.max_commits}, Max Diff: {self.max_dev_diff}, Max Files: {self.max_files_count}')

    def print_scores(self):
        all_pulls = (self.mbedtls_pulls + self.restricted_pulls)
        sorted_pulls = sorted(all_pulls, key=lambda x: x.score, reverse=True)
        for pr in sorted_pulls:
            text = f'{pr.repo_name}/{pr.number}:'
            spacing = ' ' * (30- len(text))
            print(f'{text}{spacing}{pr.score}')


def calculate_score(norm_metrics):
    # Placeholder: divide bytes saved by the average of the rest of the
    # metrics (equal weighting)
    s = norm_metrics['commits'] + norm_metrics['files_count'] + \
            norm_metrics['lines_changed'] + norm_metrics['dev_diff']
    return norm_metrics['bytes_saved']/(s/4)

def check_args(args):
    '''Verify that all arguments passed to the script are valid

    Checks that the JSON path is valid and points to a JSON file.
    Checks that the repo paths are valid and point to git repositories.

    Args:
    * args: object containing arguments passed to script
    '''
    if not args.json_path.endswith('.json') and \
       not os.path.exists(args.json_path):
        raise ValueError(f'{path} is not a valid path to a JSON file')

    for path in [args.mbedtls_path, args.restricted_path]:
        if not os.path.exists(path):
            raise ValueError(f'{path}: No such file or directory')
        else:
            ret = subprocess.run(f'cd {path}; git status', shell=True,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.STDOUT)
            if ret.returncode != 0:
                raise ValueError(f'{path} is not a path to a git repository. Ret = {ret}')


def main():
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json_path', metavar='PR_TABLE',
                        help='Path to a JSON file containing the PR table')
    parser.add_argument('mbedtls_path', metavar='MBEDTLS_PATH',
                        help='Path to the root of the mbedtls repository')
    parser.add_argument('restricted_path', metavar='MBEDTLS_RESTRICTED_PATH',
                        help='Path to the root of the mbedtls-restricted'
                             ' repository')
    # parser.add_argument('--no-checkout', action='store_true',
    #                     help="Don't checkout all PRs before collecting metrics.\
    #                      Use this when you already have all PRs locally.")
    args = parser.parse_args()

    check_args(args)

    pr_getter = PullRequestGetter(args.json_path, args.mbedtls_path, args.restricted_path)
    pr_getter.get_metrics()
    pr_getter.normalise_metrics()
    #pr_getter.print_pulls()
    pr_getter.print_scores()

if __name__ == '__main__':
    main()