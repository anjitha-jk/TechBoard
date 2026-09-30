from pydantic import BaseModel
from typing import List

class RepoData(BaseModel):
    name: str
    html_url: str
    description: str | None
    stargazers_count: int
    language: str | None


class GitHubProfile(BaseModel):
    meta_data: dict
    username: str
    name: str | None
    avatar_url: str
    bio: str | None
    public_repos: int
    followers: int
    top_repositories: List[RepoData]

class CommitInfo(BaseModel):
    sha:str
    repo_name: str
    commit_time: str
    additions: int
    deletions: int
    languages_used : List[str]

class PRTurnaround(BaseModel):
    repo_name: str
    title: str
    cycle_time_hours:float
    is_bottleneck: bool

class GitHubStats(BaseModel):
    summary: dict
    commit_history: List[CommitInfo]
    pr_turnaround: List[PRTurnaround]