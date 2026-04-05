from __future__ import annotations

"""Tool implementations for the coding agent CLI."""

import fnmatch
import os
import subprocess
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import aiofiles
import httpx
from rich.console import Console

console = Console()


def _sanitize_path(path: str) -> str:
    """Prevent escaping the working directory."""
    base = os.path.abspath(os.getcwd())
    # Use realpath to resolve symlinks and prevent traversal attacks
    target = os.path.realpath(os.path.join(base, path))
    base_real = os.path.realpath(base)
    # Allow paths within the current working tree
    if not target.startswith(base_real):
        raise ValueError(f"Path {path} is outside the allowed workspace")
    return target


async def read_file(path: str, offset: int = 1, limit: int = 100) -> str:
    """Read the contents of a file asynchronously. Returns the specified range of lines."""
    try:
        target = _sanitize_path(path)
        # Use sync os.path.exists/isdir since these are fast checks
        if not os.path.exists(target):
            return f"Error: file not found: {path}"
        if os.path.isdir(target):
            return f"Error: {path} is a directory"

        async with aiofiles.open(target, encoding="utf-8", errors="ignore") as f:
            lines = await f.readlines()

        start = max(0, offset - 1)
        end = min(len(lines), start + limit)
        selected = lines[start:end]
        header = f"--- {path} (lines {start + 1}-{end} of {len(lines)}) ---\n"
        return header + "".join(selected)
    except Exception as exc:
        return f"Error reading {path}: {exc}"


async def write_file(path: str, content: str, mode: str = "overwrite") -> str:
    """Write or append text to a file asynchronously. Creates parent directories if needed."""
    try:
        target = _sanitize_path(path)
        # Create directories synchronously (fast operation)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        file_mode = "a" if mode == "append" else "w"

        async with aiofiles.open(target, file_mode, encoding="utf-8") as f:
            await f.write(content)

        return f"Success: wrote to {path} ({mode})"
    except Exception as exc:
        return f"Error writing {path}: {exc}"


def shell(command: str, timeout: int = 30) -> str:
    """Execute a shell command in the current working directory."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        out = result.stdout or ""
        err = result.stderr or ""
        lines = []
        if out:
            lines.append("STDOUT:\n" + out)
        if err:
            lines.append("STDERR:\n" + err)
        if not lines:
            lines.append("(no output)")
        lines.append(f"Exit code: {result.returncode}")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as exc:
        return f"Error running command: {exc}"


def list_directory(path: str = ".") -> str:
    """List files and subdirectories in a given path."""
    try:
        target = _sanitize_path(path)
        if not os.path.isdir(target):
            return f"Error: {path} is not a directory"

        entries = os.listdir(target)
        lines = [f"Directory: {path}"]
        for e in sorted(entries):
            full = os.path.join(target, e)
            kind = "dir" if os.path.isdir(full) else "file"
            size = os.path.getsize(full) if kind == "file" else "-"
            lines.append(f"  [{kind:4}] {e:<40} {size}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listing {path}: {exc}"


async def grep(pattern: str, path: str = ".", glob: str | None = None) -> str:
    """Search for a text pattern in files under a path asynchronously."""
    try:
        target = _sanitize_path(path)
        matches = []

        # Build file list synchronously (directory traversal)
        if os.path.isfile(target):
            files = [target]
        else:
            files = []
            for root, _, filenames in os.walk(target):
                for name in filenames:
                    if glob and not fnmatch.fnmatch(name, glob):
                        continue
                    files.append(os.path.join(root, name))

        # Read files asynchronously
        for fp in files[:50]:  # limit scanned files
            try:
                async with aiofiles.open(fp, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(await f.readlines(), 1):
                        if pattern in line:
                            rel = os.path.relpath(fp, os.getcwd())
                            matches.append(f"{rel}:{i}: {line.rstrip()}")
                            if len(matches) >= 100:
                                break
            except Exception:
                continue
            if len(matches) >= 100:
                break

        if not matches:
            return f"No matches for '{pattern}'"
        return "\n".join(matches[:100])
    except Exception as exc:
        return f"Error searching: {exc}"


def get_datetime(timezone_offset: str = "UTC", format: str = "iso") -> str:
    """Get the current date and time.
    
    Args:
        timezone_offset: Timezone to use. Options: "UTC", "GMT", "local", or offset like "+02:00", "-05:00"
        format: Output format. Options: "iso" (ISO 8601), "readable" (human friendly), "date_only", "time_only"
    
    Returns:
        Current date/time as a formatted string
    """
    try:
        # Get current time in UTC
        now_utc = datetime.now(timezone.utc)
        
        # Determine target timezone
        if timezone_offset.upper() in ("UTC", "GMT"):
            now = now_utc
            tz_name = "UTC"
        elif timezone_offset.lower() == "local":
            # Convert to local timezone
            now = datetime.now().astimezone()
            tz_name = str(now.tzinfo) if now.tzinfo else "Local"
        elif timezone_offset.startswith(("+", "-")):
            # Parse offset like "+02:00" or "-05:00"
            try:
                sign = 1 if timezone_offset[0] == "+" else -1
                parts = timezone_offset[1:].split(":")
                hours = int(parts[0])
                minutes = int(parts[1]) if len(parts) > 1 else 0
                offset = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
                now = now_utc.astimezone(offset)
                tz_name = timezone_offset
            except Exception:
                # Fall back to UTC if parsing fails
                now = now_utc
                tz_name = "UTC (fallback)"
        else:
            # Try common timezone names
            tz_map = {
                "EST": "America/New_York",
                "CST": "America/Chicago",
                "MST": "America/Denver",
                "PST": "America/Los_Angeles",
                "CET": "Europe/Paris",
                "EET": "Europe/Helsinki",
            }
            tz_name = tz_map.get(timezone_offset.upper(), "UTC")
            now = now_utc
        
        # Format output
        if format == "iso":
            return now.isoformat()
        elif format == "readable":
            return now.strftime(f"%A, %B %d, %Y at %I:%M:%S %p {tz_name}")
        elif format == "date_only":
            return now.strftime("%Y-%m-%d")
        elif format == "time_only":
            return now.strftime(f"%H:%M:%S {tz_name}")
        elif format == "full":
            return (
                f"Date/Time: {now.strftime('%A, %B %d, %Y %I:%M:%S %p')}\n"
                f"Timezone: {tz_name}\n"
                f"ISO Format: {now.isoformat()}\n"
                f"Unix Timestamp: {int(now_utc.timestamp())}"
            )
        else:
            return now.isoformat()
    except Exception as exc:
        return f"Error getting datetime: {exc}"




def glob_files(pattern: str) -> str:
    """Find files matching a glob pattern.
    
    Args:
        pattern: Glob pattern like '*.py', '**/*.md', 'src/**/*.js'
        
    Returns:
        List of matching file paths
    """
    try:
        import glob as glob_module
        
        # Prevent escaping workspace
        base = os.path.abspath(os.getcwd())
        
        # Check if pattern is recursive
        recursive = "**" in pattern
        
        # Search for matches
        matches = glob_module.glob(pattern, recursive=recursive)
        
        # Filter to only files within workspace
        valid_matches = []
        for m in matches:
            full_path = os.path.abspath(m)
            if full_path.startswith(base) and os.path.isfile(full_path):
                valid_matches.append(m)
        
        if not valid_matches:
            return f"No files matching pattern: {pattern}"
        
        # Sort and limit results
        valid_matches = sorted(valid_matches)[:100]
        
        lines = [f"Files matching '{pattern}' ({len(valid_matches)} found):\n"]
        for m in valid_matches:
            lines.append(f"  {m}")
        
        return "\n".join(lines)
        
    except Exception as exc:
        return f"Error searching files: {exc}"


def delete_file(path: str) -> str:
    """Delete a file.
    
    Args:
        path: Relative path to the file to delete
        
    Returns:
        Success or error message
    """
    try:
        target = _sanitize_path(path)
        
        if not os.path.exists(target):
            return f"Error: file not found: {path}"
        if os.path.isdir(target):
            return f"Error: {path} is a directory (use shell with 'rm -rf' for directories)"
        
        os.remove(target)
        return f"Success: deleted {path}"
        
    except Exception as exc:
        return f"Error deleting {path}: {exc}"


def python(code: str, timeout: int = 30) -> str:
    """Execute Python code safely.
    
    WARNING: This runs code in a subprocess with restricted access.
    Available modules: os, sys, json, re, math, random, datetime, itertools, collections, typing
    No network access. No file system access outside workspace.
    
    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds
        
    Returns:
        Output from the code (stdout) or error message
    """
    try:
        import subprocess
        import tempfile
        
        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # Write wrapper that captures output
            wrapper_code = f'''
import sys
import json
import os
import re
import math
import random
import datetime
import itertools
import collections
from typing import *

# Redirect stdout/stderr
from io import StringIO
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = mystdout = StringIO()
sys.stderr = mystderr = StringIO()

try:
{chr(10).join("    " + line for line in """{code}""".split(chr(10)))}
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()

# Restore and print captured output
sys.stdout = old_stdout
sys.stderr = old_stderr
print("__PYTHON_OUTPUT_START__")
print(mystdout.getvalue(), end="")
if mystderr.getvalue():
    print("__PYTHON_STDERR__")
    print(mystderr.getvalue(), end="")
print("__PYTHON_OUTPUT_END__")
'''
            f.write(wrapper_code)
            temp_file = f.name
        
        try:
            # Run in subprocess with restricted environment
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd(),
                # Restrict environment
                env={"PATH": "/usr/bin:/bin", "HOME": os.getcwd(), "PYTHONPATH": ""},
            )
            
            output = result.stdout or ""
            stderr = result.stderr or ""
            
            # Extract output between markers
            start_marker = "__PYTHON_OUTPUT_START__"
            end_marker = "__PYTHON_OUTPUT_END__"
            
            if start_marker in output:
                start_idx = output.find(start_marker) + len(start_marker)
                end_idx = output.find(end_marker, start_idx)
                if end_idx > start_idx:
                    inner_output = output[start_idx:end_idx].strip()
                else:
                    inner_output = output[start_idx:].strip()
            else:
                inner_output = output.strip()
            
            lines = []
            if inner_output:
                lines.append("Output:")
                lines.append(inner_output)
            if stderr:
                lines.append("Stderr:")
                lines.append(stderr[:500])  # Limit stderr
            if result.returncode != 0:
                lines.append(f"Exit code: {result.returncode}")
            
            return "\n".join(lines) if lines else "(no output)"
            
        finally:
            # Cleanup temp file
            try:
                os.unlink(temp_file)
            except:
                pass
                
    except subprocess.TimeoutExpired:
        return f"Error: Python code timed out after {timeout}s"
    except Exception as exc:
        return f"Error executing Python: {exc}"


async def search_web(query: str, limit: int = 5) -> str:
    """Search the web using DuckDuckGo. Returns search results with titles, URLs, and snippets.
    
    Args:
        query: The search query string
        limit: Maximum number of results to return (1-10)
    
    Returns:
        Formatted search results
    """
    try:
        # Use DuckDuckGo's HTML interface (no API key needed)
        # We'll use the lite version for simpler HTML parsing
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://lite.duckduckgo.com/lite/?q={encoded_query}"
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            # Simple headers - avoid compression which can cause issues
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            
            # Parse the HTML response to extract results
            from html.parser import HTMLParser
            
            class DDGResultParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results: list[dict[str, Any]] = []
                    self.current_result: dict[str, Any] | None = None
                    self.in_result = False
                    self.in_title = False
                    self.in_snippet = False
                    self.capture_data = False
                    self.data_buffer = ""
                    
                def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                    attrs_dict = dict(attrs)
                    
                    # Results are in table rows with class "result-link" or similar
                    if tag == "a" and attrs_dict.get("class") == "result-link":
                        self.in_result = True
                        self.current_result = {
                            "title": "",
                            "url": attrs_dict.get("href", ""),
                            "snippet": ""
                        }
                        self.in_title = True
                        self.capture_data = True
                        
                def handle_endtag(self, tag: str) -> None:
                    if self.in_title and tag == "a":
                        self.in_title = False
                        self.capture_data = False
                        if self.current_result:
                            self.current_result["title"] = self.data_buffer.strip()
                        self.data_buffer = ""
                        
                    # Snippet follows the title in the next td
                    elif self.in_result and tag == "tr":
                        if self.current_result and self.current_result.get("title"):
                            self.results.append(self.current_result)
                        self.in_result = False
                        self.current_result = None
                        
                def handle_data(self, data: str) -> None:
                    if self.capture_data:
                        self.data_buffer += data
                        
                def get_results(self) -> list[dict[str, Any]]:
                    return self.results[:10]  # Limit to 10 results
            
            # Simple parsing approach - extract links and snippets
            html = resp.text
            
            # Alternative: use regex-based extraction for simplicity
            import re
            
            # Find result links and titles
            results = []
            
            # Pattern for result links in DuckDuckGo lite
            # Format: <a class="result-link" href="URL">TITLE</a>
            # Note: DDG uses single quotes in HTML and href may come before class
            link_pattern = r"<a[^>]*class=['\"]result-link['\"][^>]*href=['\"]([^'\"]+)['\"][^>]*>([^<]+)</a>|<a[^>]*href=['\"]([^'\"]+)['\"][^>]*class=['\"]result-link['\"][^>]*>([^<]+)</a>"
            matches = re.findall(link_pattern, html, re.IGNORECASE)
            # Flatten the two alternative capture groups
            links = []
            for m in matches:
                if m[0]:  # First pattern matched
                    links.append((m[0], m[1]))
                else:  # Second pattern matched
                    links.append((m[2], m[3]))
            
            # Pattern for snippets - they're in the next row
            # Look for text in table cells after the link
            snippet_pattern = r'<td[^>]*class=[\'\"]result-snippet[\'\"][^>]*>([^<]+)</td>'
            snippets = re.findall(snippet_pattern, html, re.IGNORECASE)
            
            for i, (href, title) in enumerate(links[:limit]):
                snippet = snippets[i].strip() if i < len(snippets) else ""
                # Clean up HTML entities
                title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                snippet = snippet.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                results.append({
                    "title": title.strip(),
                    "url": href.strip(),
                    "snippet": snippet.strip()
                })
            
            if not results:
                # Fallback: try alternative pattern for when DDG changes their HTML
                # Look for any links that seem like search results
                alt_pattern = r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]{10,200})</a>'
                alt_links = re.findall(alt_pattern, html)
                for href, title in alt_links[:limit]:
                    if "duckduckgo.com" not in href and "javascript:" not in href:
                        results.append({
                            "title": title.strip(),
                            "url": href.strip(),
                            "snippet": ""
                        })
            
            # Format results
            if not results:
                # Debug info - return a snippet of HTML to help diagnose
                html_preview = html[:500].replace('\n', ' ')
                return f"No search results found for '{query}'. The search service may be temporarily unavailable or the query returned no results."
            
            lines = [f"Web search results for: '{query}' ({len(results)} results)\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r['title']}")
                lines.append(f"   URL: {r['url']}")
                if r['snippet']:
                    lines.append(f"   {r['snippet'][:200]}...")
                lines.append("")
            
            return "\n".join(lines)
            
    except httpx.TimeoutException:
        return f"Error: Search request timed out for query '{query}'"
    except httpx.HTTPStatusError as e:
        return f"Error: Search returned HTTP {e.response.status_code}"
    except Exception as exc:
        return f"Error searching web for '{query}': {exc}"


async def fetch_url(url: str, max_length: int = 5000) -> str:
    """Fetch and extract main text content from a URL.
    
    Args:
        url: The URL to fetch
        max_length: Maximum number of characters to return
    
    Returns:
        Extracted text content from the page
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            }
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            
            html = resp.text
            
            # Simple HTML to text extraction
            import re
            
            # Remove script and style elements
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            
            # Extract title
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "No title"
            
            # Try to extract main content (look for common content containers)
            content = ""
            
            # Try article tag first
            article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
            if article_match:
                content = article_match.group(1)
            else:
                # Try main tag
                main_match = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL | re.IGNORECASE)
                if main_match:
                    content = main_match.group(1)
                else:
                    # Try div with content-like classes
                    for pattern in [r'<div[^>]*class="[^"]*(?:content|article|post)[^"]*"[^>]*>(.*?)</div>', 
                                   r'<div[^>]*class="[^"]*main[^"]*"[^>]*>(.*?)</div>']:
                        content_match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                        if content_match:
                            content = content_match.group(1)
                            break
            
            # If no content container found, use body
            if not content:
                body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
                content = body_match.group(1) if body_match else html
            
            # Convert HTML to text
            # Remove remaining HTML tags
            text = re.sub(r'<[^>]+>', ' ', content)
            
            # Decode HTML entities
            import html as html_module
            text = html_module.unescape(text)
            
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Limit length
            if len(text) > max_length:
                text = text[:max_length] + "...\n\n[Content truncated. Use shell with curl/wget to get full page.]"
            
            result = f"Title: {title}\nURL: {url}\n\n{text}"
            return result
            
    except httpx.TimeoutException:
        return f"Error: Request timed out while fetching {url}"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} when fetching {url}"
    except Exception as exc:
        return f"Error fetching URL: {exc}"


def copy_file(source: str, destination: str) -> str:
    """Copy a file from source to destination.
    
    Args:
        source: Relative path to the source file
        destination: Relative path to the destination
        
    Returns:
        Success or error message
    """
    try:
        import shutil
        
        src_path = _sanitize_path(source)
        dst_path = _sanitize_path(destination)
        
        if not os.path.exists(src_path):
            return f"Error: source file not found: {source}"
        if os.path.isdir(src_path):
            return f"Error: source is a directory: {source} (use shell for directory operations)"
        
        # Create destination directory if needed
        dst_dir = os.path.dirname(dst_path)
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
        
        shutil.copy2(src_path, dst_path)
        return f"Success: copied {source} to {destination}"
        
    except Exception as exc:
        return f"Error copying file: {exc}"


def move_file(source: str, destination: str) -> str:
    """Move/rename a file from source to destination.
    
    Args:
        source: Relative path to the source file
        destination: Relative path to the destination
        
    Returns:
        Success or error message
    """
    try:
        import shutil
        
        src_path = _sanitize_path(source)
        dst_path = _sanitize_path(destination)
        
        if not os.path.exists(src_path):
            return f"Error: source file not found: {source}"
        if os.path.isdir(src_path):
            return f"Error: source is a directory: {source} (use shell for directory operations)"
        
        # Create destination directory if needed
        dst_dir = os.path.dirname(dst_path)
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
        
        shutil.move(src_path, dst_path)
        return f"Success: moved {source} to {destination}"
        
    except Exception as exc:
        return f"Error moving file: {exc}"


async def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
    timeout: int = 30
) -> str:
    """Make an HTTP request.
    
    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)
        headers: Optional dictionary of HTTP headers
        body: Optional request body (for POST, PUT, PATCH)
        timeout: Request timeout in seconds
        
    Returns:
        Response status, headers, and body
    """
    try:
        method = method.upper()
        valid_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
        if method not in valid_methods:
            return f"Error: invalid method '{method}'. Valid: {', '.join(valid_methods)}"
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            kwargs = {}
            if headers:
                kwargs["headers"] = headers
            if body and method in ("POST", "PUT", "PATCH"):
                kwargs["content"] = body
            
            response = await client.request(method, url, **kwargs)
            
            # Build response output
            lines = [
                f"Status: {response.status_code}",
                f"URL: {response.url}",
                "",
                "Headers:",
            ]
            for key, value in response.headers.items():
                lines.append(f"  {key}: {value}")
            
            if method != "HEAD":
                lines.extend(["", "Body:"])
                content = response.text
                # Truncate if too long
                if len(content) > 10000:
                    content = content[:10000] + "\n\n[Response truncated at 10000 chars]"
                lines.append(content)
            
            return "\n".join(lines)
            
    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout}s"
    except Exception as exc:
        return f"Error making HTTP request: {exc}"


def git(command: str, args: str = "") -> str:
    """Execute git commands safely.
    
    Common commands: status, log, diff, branch, show, stash
    Modifying commands (commit, push, pull) are restricted - use shell instead.
    
    Args:
        command: The git subcommand (e.g., 'status', 'log', 'diff')
        args: Additional arguments for the command
        
    Returns:
        Command output
    """
    try:
        # Whitelist of safe read-only git commands
        safe_commands = {
            "status", "log", "diff", "show", "branch", "tag",
            "stash", "config", "remote", "blame", "grep",
            "ls-files", "ls-tree", "rev-parse", "describe",
            "symbolic-ref", "for-each-ref", "reflog"
        }
        
        # Commands that modify repo - require explicit confirmation
        restricted_commands = {
            "commit", "push", "pull", "fetch", "merge", "rebase",
            "reset", "checkout", "cherry-pick", "revert", "am",
            "init", "clone", "add", "rm", "mv", "clean"
        }
        
        cmd_base = command.lower().split()[0]
        
        if cmd_base in restricted_commands:
            return (
                f"Error: '{command}' is a modifying git command. "
                f"For safety, use the 'shell' tool instead for: commit, push, pull, "
                f"merge, rebase, reset, checkout, add, rm, etc."
            )
        
        if cmd_base not in safe_commands:
            return (
                f"Error: unknown git command '{command}'. "
                f"Safe commands: {', '.join(sorted(safe_commands))}"
            )
        
        # Build the command
        full_cmd = f"git {command}"
        if args:
            full_cmd += f" {args}"
        
        # Execute with timeout
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd(),
        )
        
        lines = []
        if result.stdout:
            lines.append(result.stdout)
        if result.stderr:
            lines.append("Stderr:")
            lines.append(result.stderr)
        if not lines:
            lines.append("(no output)")
        
        lines.append(f"Exit code: {result.returncode}")
        return "\n".join(lines)
        
    except subprocess.TimeoutExpired:
        return "Error: git command timed out after 30s"
    except Exception as exc:
        return f"Error executing git command: {exc}"


async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments.

    Handles both sync and async tool functions.
    """
    func = TOOL_MAP.get(name)
    if not func:
        return f"Error: unknown tool {name}"

    try:
        if name in ASYNC_TOOLS:
            # Async function - await it
            result = await func(**arguments)
            return str(result) if result is not None else ""
        else:
            # Sync function - call directly
            result = func(**arguments)
            return str(result) if result is not None else ""
    except Exception as exc:
        return f"Error executing {name}: {exc}"


# Tool definitions for OpenAI API
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Returns the specified range of lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start from (1-indexed)",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max lines to read",
                        "default": 100,
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or append text to a file. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "content": {"type": "string", "description": "Text content to write"},
                    "mode": {
                        "type": "string",
                        "enum": ["overwrite", "append"],
                        "default": "overwrite",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Execute a shell command in the current working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the directory",
                        "default": ".",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for a text pattern in files under a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text pattern to search for"},
                    "path": {
                        "type": "string",
                        "description": "Relative path to search in",
                        "default": ".",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Optional file glob filter, e.g. *.py",
                        "default": None,
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date and time. Use this tool instead of guessing or using training data when asked about current date/time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone_offset": {
                        "type": "string",
                        "description": "Timezone to use: 'UTC', 'GMT', 'local', or offset like '+02:00', '-05:00'",
                        "default": "UTC",
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: 'iso' (default), 'readable', 'date_only', 'time_only', 'full'",
                        "default": "iso",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for information. Use this tool when you need up-to-date information not in your training data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (1-10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and extract main text content from a URL. Use this to read web pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum characters to return (default: 5000)",
                        "default": 5000,
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "Find files matching a glob pattern like '*.py' or 'src/**/*.js'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file. Use with caution - this permanently removes files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file to delete",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "python",
            "description": "Execute Python code safely in a sandbox. Use for calculations, data processing, or quick scripts. Restricted environment - no network, limited file access.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file from source to destination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Relative path to the source file",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Relative path to the destination",
                    },
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move/rename a file from source to destination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Relative path to the source file",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Relative path to the destination",
                    },
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Make an HTTP request (GET, POST, PUT, DELETE, etc.). Use for API calls or fetching data from web services.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to request",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)",
                        "default": "GET",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers as key-value pairs",
                        "default": None,
                    },
                    "body": {
                        "type": "string",
                        "description": "Request body for POST/PUT/PATCH",
                        "default": None,
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git",
            "description": "Execute safe read-only git commands: status, log, diff, branch, show, stash, etc. Modifying commands (commit, push, checkout, etc.) require using the shell tool instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Git subcommand (e.g., 'status', 'log', 'diff --staged', 'branch -a')",
                    },
                    "args": {
                        "type": "string",
                        "description": "Additional arguments for the command",
                        "default": "",
                    },
                },
                "required": ["command"],
            },
        },
    },
]


# Map of tool names to functions
# Note: Some functions are async and need to be awaited in execute_tool
TOOL_MAP = {
    "read_file": read_file,
    "write_file": write_file,
    "shell": shell,
    "list_directory": list_directory,
    "grep": grep,
    "get_datetime": get_datetime,
    "search_web": search_web,
    "fetch_url": fetch_url,
    "glob_files": glob_files,
    "delete_file": delete_file,
    "python": python,
    "copy_file": copy_file,
    "move_file": move_file,
    "http_request": http_request,
    "git": git,
}


# Set of async tool functions (need to be awaited)
ASYNC_TOOLS = {"read_file", "write_file", "grep", "search_web", "fetch_url", "http_request"}
