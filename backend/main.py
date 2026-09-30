import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from type import GitHubStats, GitHubProfile, RepoData, CommitInfo, PRTurnaround
from typing import List
from datetime import datetime, timedelta

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/api/github/{username}")
async def get_github_data(username: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "FastAPI-App",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            user_url = f"https://api.github.com/users/{username}"
            user_response = await client.get(user_url, headers=headers)

            if user_response.status_code == 404:
                raise HTTPException(status_code=404, detail="GitHub user not found")
            elif user_response.status_code != 200:
                raise HTTPException(
                    status_code=user_response.status_code,
                    detail="Failed to fetch user data",
                )

            try:
                user_data = user_response.json()
            except ValueError as exc:
                raise HTTPException(
                    status_code=502, detail="Invalid response from GitHub API"
                ) from exc

            repos_url = (
                f"https://api.github.com/users/{username}/repos?sort=stars&per_page=5"
            )
            repos_response = await client.get(repos_url, headers=headers)
            repos_data = (
                repos_response.json() if repos_response.status_code == 200 else []
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="GitHub request failed") from exc

    top_repos = [
        RepoData(
            name=repo["name"],
            html_url=repo["html_url"],
            description=repo.get("description"),
            stargazers_count=repo["stargazers_count"],
            language=repo.get("language"),
        )
        for repo in repos_data
    ]

    return GitHubProfile(
        meta_data=user_data,
        username=user_data["login"],
        name=user_data.get("name"),
        avatar_url=user_data["avatar_url"],
        bio=user_data.get("bio"),
        public_repos=user_data["public_repos"],
        followers=user_data["followers"],
        top_repositories=top_repos,
    )

# Helper functions for GitHub analytics - Optimized REST API approach
async def fetch_analytics_data(
    client: httpx.AsyncClient, username: str, headers: dict
) -> tuple[List[CommitInfo], List[PRTurnaround]]:
    """Fetch analytics using efficient REST API calls only."""
    
    commit_history: List[CommitInfo] = []
    pr_turnaround: List[PRTurnaround] = []
    
    try:
        # Step 1: Fetch top 3 repos sorted by update date (1 API call)
        repos_url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=3&type=owner"
        repos_res = await client.get(repos_url, headers=headers)
        
        if repos_res.status_code != 200:
            raise HTTPException(
                status_code=repos_res.status_code,
                detail=f"Failed to fetch repositories"
            )
        
        repos = repos_res.json()
        if not repos:
            return commit_history, pr_turnaround
        
        # Process each repo (limit to 3 to avoid rate limits)
        for repo in repos[:3]:
            repo_name = repo["name"]
            
            # Step 2: Fetch commits with built-in stats (1 call per repo)
            commits_url = f"https://api.github.com/repos/{username}/{repo_name}/commits?per_page=5"
            commits_res = await client.get(commits_url, headers=headers)
            
            if commits_res.status_code == 200:
                try:
                    for commit_item in commits_res.json():
                        commit_history.append(CommitInfo(
                            sha=commit_item["sha"][:7],
                            repo_name=repo_name,
                            commit_time=commit_item["commit"]["author"]["date"],
                            additions=0,  # REST list endpoint doesn't include stats
                            deletions=0,
                            languages_used=[]
                        ))
                except Exception as e:
                    print(f"Warning: Failed to parse commits for {repo_name}: {e}")
            
            # Step 3: Fetch merged PRs and calculate turnaround (1 call per repo)
            pr_url = f"https://api.github.com/repos/{username}/{repo_name}/pulls?state=closed&per_page=5"
            pr_res = await client.get(pr_url, headers=headers)
            
            if pr_res.status_code == 200:
                try:
                    for pr in pr_res.json():
                        if pr.get("merged_at"):
                            created = datetime.strptime(pr["created_at"], "%Y-%m-%dT%H:%M:%SZ")
                            merged = datetime.strptime(pr["merged_at"], "%Y-%m-%dT%H:%M:%SZ")
                            cycle_time = (merged - created).total_seconds() / 3600
                            
                            pr_turnaround.append(PRTurnaround(
                                repo_name=repo_name,
                                title=pr["title"],
                                cycle_time_hours=round(cycle_time, 2),
                                is_bottleneck=cycle_time > 48
                            ))
                except Exception as e:
                    print(f"Warning: Failed to parse PRs for {repo_name}: {e}")
    
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, 
            detail=f"Failed to fetch analytics: {str(exc)}"
        )
    
    return commit_history, pr_turnaround


def calculate_analytics_summary(
    commit_history: List[CommitInfo], 
    pr_turnaround: List[PRTurnaround]
) -> dict:
    """Generate high-level summary analytics."""
    total_additions = sum(c.additions for c in commit_history)
    avg_turnaround = (
        sum(p.cycle_time_hours for p in pr_turnaround) / len(pr_turnaround)
        if pr_turnaround
        else 0
    )

    return {
        "total_commits_profiled": len(commit_history),
        "lines_added_volume": total_additions,
        "average_review_turnaround_hours": round(avg_turnaround, 1),
        "process_bottlenecks_flagged": sum(1 for p in pr_turnaround if p.is_bottleneck)
    }


@app.get("/api/github/{username}/analytics", response_model=GitHubStats)
async def get_github_stats(username: str):
    """Fetch GitHub analytics using efficient REST API calls."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "FastAPI-App",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            commit_history, pr_turnaround = await fetch_analytics_data(client, username, headers)
    
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, 
            detail=f"Failed to fetch GitHub analytics: {str(exc)}"
        )

    # Generate summary analytics
    summary = calculate_analytics_summary(commit_history, pr_turnaround)

    return GitHubStats(
        summary=summary,
        commit_history=commit_history,
        pr_turnaround=pr_turnaround
    )