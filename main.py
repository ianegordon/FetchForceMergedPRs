import requests
import datetime
import argparse
import json as json_module
import calendar
import sys

# GitHub API base URL
github_api_url = "https://api.github.com"

def get_merged_prs(repo, start_date, end_date, token, verbose):
    """
    Fetch all PRs merged in `repo` within [start_date, end_date] using the
    Search API, so merge-date filtering happens server-side. This avoids the
    /pulls endpoint, which cannot sort by merge date.
    """
    prs = []
    page = 1
    query = (
        f"repo:{repo} is:pr is:merged "
        f"merged:{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}"
    )

    while True:
        url = f"{github_api_url}/search/issues"
        params = {"q": query, "per_page": 100, "page": page}
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        total_count = data.get("total_count", 0)
        items = data.get("items", [])
        if not items:
            break

        for item in items:
            merged_at_str = item.get("pull_request", {}).get("merged_at")
            if not merged_at_str:
                continue
            merged_at = datetime.datetime.strptime(merged_at_str, "%Y-%m-%dT%H:%M:%SZ")
            # `merged:` is date-granular; re-check exact bounds (start 00:00:00,
            # end 23:59:59) so the window matches the CLI semantics precisely.
            if start_date <= merged_at <= end_date:
                item["merged_at"] = merged_at_str  # normalize to the shape main() reads
                prs.append(item)
                if verbose:
                    print(f"Adding PR {item['number']} merged at {merged_at}")
            elif verbose:
                print(f"Skipping PR {item['number']} merged at {merged_at} (outside exact window)")

        # Search returns at most 1000 results (10 pages of 100); page 11 would 422.
        if page * 100 >= min(total_count, 1000):
            if total_count > 1000:
                print(
                    f"WARNING: {total_count} merged PRs match but the Search API "
                    f"caps results at 1000. Narrow the date range to capture all.",
                    file=sys.stderr,
                )
            break
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
            formatted_pr_merged_date = pr["merged_at"].split("T")[0]
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
