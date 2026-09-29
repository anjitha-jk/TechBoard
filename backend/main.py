import os
from typing import List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
