import requests
import datetime
import argparse
import json as json_module
import calendar

# GitHub API base URL
github_api_url = "https://api.github.com"

def get_merged_prs(repo, start_date, end_date, token, verbose):
    """
    Fetch all merged PRs in the given repository within the specified date range.
    """
    prs = []
    page = 1

    shouldContinue = True

    while shouldContinue:
        url = f"{github_api_url}/repos/{repo}/pulls"
        params = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
            "page": page
        }
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            break

        for pr in data:
            if pr.get("merged_at"):
                merged_at = datetime.datetime.strptime(pr["merged_at"], "%Y-%m-%dT%H:%M:%SZ")
                if start_date <= merged_at <= end_date:
                    pr_number = pr["number"]
                    if verbose:
                        print(f"Adding PR {pr_number} for {start_date} <= {merged_at} <= {end_date}")
                    prs.append(pr)
                else:
                    pr_number = pr["number"]
                    if verbose:
                        print(f"Skipping PR {pr_number} for {start_date} <= {merged_at} <= {end_date}")

            if merged_at < start_date:
                shouldContinue = False

        page += 1

    return prs

def get_comments(repo, pr_number, token):
    """
    Fetch all comments for a given PR.
    """
    url = f"{github_api_url}/repos/{repo}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {token}"} if token else {}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def calculate_enddate_if_needed(start_date, end_date):
    """
    Automatically calculate the end date if not provided.
    If the start date is the first day of the month, set the end date to the last day of the month at midnight.
    Otherwise, set the end date to midnight 30 days after the start date.
    """
    if end_date is None:
        if start_date.day == 1:
            last_day = calendar.monthrange(start_date.year, start_date.month)[1]
            return start_date.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
        else:
            return (start_date + datetime.timedelta(days=30)).replace(hour=23, minute=59, second=59, microsecond=999999)
    return end_date

def main(repo, start_date, end_date, token, output_json, verbose):
    """
    Main script logic.
    """
    end_date = calculate_enddate_if_needed(start_date, end_date)

    force_merged_prs = []

    if verbose:
        print(f"Fetching merged PRs for repository {repo} from {start_date} to {end_date}...")
    merged_prs = get_merged_prs(repo, start_date, end_date, token, verbose)

    if verbose:
        print(f"Scanning {len(merged_prs)} merged PRs for FORCE_MERGE comments...")
    for pr in merged_prs:
        pr_number = pr["number"]
        pr_author = pr["user"]["login"]
        pr_merged_at = pr["merged_at"]
        comments = get_comments(repo, pr_number, token)

        for comment in comments:
            if "FORCE_MERGE" in comment["body"]:
                force_merged_prs.append({
                    "repo": repo,
                    "pr_number": pr_number,
                    "title": pr["title"],
                    "author": pr_author,
                    "commenter": comment["user"]["login"],
                    "comment_body": comment["body"],
                    "merged_at": pr_merged_at,
                    "url": pr["html_url"]
                })

    if output_json:
        print(json_module.dumps(force_merged_prs, indent=4))
    else:
        print("\nForce-Merged PRs:")
        for pr in force_merged_prs:
            formatted_pr_merged_date = pr_merged_at.split("T")[0]
            print(f"{pr['repo']}#{pr['pr_number']}: {pr['author']} - {pr['title']} @ {formatted_pr_merged_date}")
            print(f"Comment by {pr['commenter']}: {pr['comment_body']}")
            print(f"URL: {pr['url']}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find PRs force-merged in a GitHub repository.")
    parser.add_argument("repo", help="GitHub repository in the format 'owner/repo'")
    parser.add_argument("--startdate", type=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0),
                        default=(datetime.datetime.now() - datetime.timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0),
                        help="Start date in YYYY-MM-DD format (default: 30 days ago at 00:00)")
    parser.add_argument("--enddate", type=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999),
                        help="End date in YYYY-MM-DD format (optional, automatically set based on start date if not provided)")
    parser.add_argument("--token", help="GitHub personal access token (optional)")
    parser.add_argument("--output_json", action="store_true", help="Output results as JSON instead of text")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    main(args.repo, args.startdate, args.enddate, args.token, args.output_json, args.verbose)
