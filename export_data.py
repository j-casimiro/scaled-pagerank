#!/usr/bin/env python3
"""
Exporter script for Wikipedia PageRank search engine data.
Crawls Wikipedia, builds TF-IDF, and exports everything to data.js.
"""

import os
import json
import time
import re
import math
import urllib.parse
import requests
from bs4 import BeautifulSoup

# Standard English stop words
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's",
    "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm",
    "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't",
    "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't",
    "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's",
    "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
    "yourselves"
}

BLACKLIST_PREFIXES = (
    "wikipedia:", "file:", "help:", "category:", "special:", "talk:", "portal:",
    "template:", "template_talk:", "book:", "draft:", "module:", "mediawiki:",
    "user:", "user_talk:", "category_talk:", "special:", "wp:", "talk:",
    
)


def normalize_wiki_title(url):
    if '/wiki/' in url:
        title_part = url.split('/wiki/')[-1]
    else:
        title_part = url
    title_part = title_part.split('#')[0]
    title_part = title_part.split('?')[0]
    title_part = title_part.replace(' ', '_').replace('%20', '_')
    title_part = urllib.parse.unquote(title_part)
    return title_part.strip().lower()


class WikiCrawler:
    def __init__(self, limit=500, seed_url="https://en.wikipedia.org/wiki/History"):
        self.limit = limit
        self.seed_url = seed_url
        self.pages = {}
        self.url_to_id = {}
        self.raw_out_links = {}
        self.adjacency_list = {}
        self.headers = {
            'User-Agent': 'WikiPageRankPrototype/1.0 (contact: jehu@example.com; educational research prototype) Python-requests/2.0'
        }

    def _extract_text(self, soup):
        content_div = soup.find('div', id='mw-content-text')
        if not content_div:
            return ""
        paragraphs = content_div.find_all('p')
        return " ".join([p.get_text() for p in paragraphs])

    def _extract_links(self, soup):
        links = []
        content_div = soup.find('div', id='mw-content-text')
        if not content_div:
            return links
        for a in content_div.find_all('a', href=True):
            href = a['href']
            if href.startswith('/wiki/'):
                article_name = href[6:]
                article_name_lower = article_name.lower()
                if any(article_name_lower.startswith(prefix) for prefix in BLACKLIST_PREFIXES):
                    continue
                if article_name_lower == "main_page":
                    continue
                abs_url = f"https://en.wikipedia.org{href.split('#')[0].split('?')[0]}"
                links.append(abs_url)
        return list(set(links))

    def crawl(self):
        queue = [self.seed_url]
        visited_urls = set()

        print(f"=== Starting Exporter Crawl (Seed: {self.seed_url}, Target: {self.limit} pages) ===")

        while queue and len(self.pages) < self.limit:
            current_url = queue.pop(0)
            norm_title = normalize_wiki_title(current_url)

            if norm_title in self.url_to_id or current_url in visited_urls:
                continue
            visited_urls.add(current_url)
            time.sleep(0.15)

            try:
                print(f"[{len(self.pages) + 1}/{self.limit}] Fetching: {current_url} ... ", end="", flush=True)
                response = requests.get(current_url, headers=self.headers, timeout=5)
                if response.status_code != 200:
                    print(f"Failed (HTTP {response.status_code})")
                    continue

                canonical_url = response.url
                canonical_norm = normalize_wiki_title(canonical_url)

                if canonical_norm in self.url_to_id:
                    print(f"Redirected to crawled: {canonical_url}")
                    self.url_to_id[norm_title] = self.url_to_id[canonical_norm]
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                title_elem = soup.find('h1', id='firstHeading')
                title = title_elem.get_text() if title_elem else canonical_url.split('/wiki/')[-1].replace('_', ' ')
                
                text = self._extract_text(soup)
                if not text.strip() or len(text) < 200:
                    print("Skipped (insufficient content)")
                    continue

                out_links = self._extract_links(soup)
                page_id = len(self.pages)
                self.pages[page_id] = {
                    'url': canonical_url,
                    'title': title,
                    'text': text
                }
                self.url_to_id[canonical_norm] = page_id
                self.url_to_id[norm_title] = page_id
                self.raw_out_links[page_id] = out_links

                print(f"Success! '{title}' ({len(out_links)} out-links)")

                for link in out_links:
                    link_norm = normalize_wiki_title(link)
                    if link_norm not in self.url_to_id and link not in visited_urls:
                        if len(queue) < self.limit * 5:
                            queue.append(link)
            except Exception as e:
                print(f"Error: {e}")

        # Adjacency list
        for page_id, links in self.raw_out_links.items():
            targets = []
            for link in links:
                link_norm = normalize_wiki_title(link)
                if link_norm in self.url_to_id:
                    target_id = self.url_to_id[link_norm]
                    if target_id != page_id:
                        targets.append(target_id)
            self.adjacency_list[page_id] = list(set(targets))

        print(f"Built graph of {len(self.pages)} nodes.")
        return self.pages, self.adjacency_list


class WikiIndexer:
    def __init__(self, pages):
        self.pages = pages
        self.N = len(pages)
        self.inverted_index = {}
        self.doc_lengths = {}
        self.dfs = {}

    def _clean_text(self, text):
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.split()
        return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]

    def build_index(self):
        print("=== Indexing Pages ===")
        doc_tokens = {}
        for page_id, page_data in self.pages.items():
            tokens = self._clean_text(page_data['text'])
            self.doc_lengths[page_id] = len(tokens)
            doc_tokens[page_id] = tokens
            unique_terms = set(tokens)
            for term in unique_terms:
                self.dfs[term] = self.dfs.get(term, 0) + 1

        for page_id, tokens in doc_tokens.items():
            doc_len = self.doc_lengths[page_id]
            if doc_len == 0:
                continue
            term_counts = {}
            for token in tokens:
                term_counts[token] = term_counts.get(token, 0) + 1
            for term, count in term_counts.items():
                tf = count / doc_len
                df = self.dfs[term]
                idf = math.log(self.N / df) + 1.0
                tf_idf = tf * idf
                if term not in self.inverted_index:
                    self.inverted_index[term] = {}
                self.inverted_index[term][page_id] = tf_idf
        print(f"Indexed {len(self.inverted_index)} terms.")
        return self.inverted_index


def main():
    crawler = WikiCrawler(limit=500)
    pages, adjacency_list = crawler.crawl()
    
    indexer = WikiIndexer(pages)
    inverted_index = indexer.build_index()

    # Create dataset struct for frontend
    frontend_data = {
        "pages": [],
        "adjacency_list": adjacency_list,
        "inverted_index": inverted_index
    }

    for page_id, p in pages.items():
        # First 300 characters as snippet
        text_clean = re.sub(r'\s+', ' ', p['text']).strip()
        snippet = text_clean[:300] + "..." if len(text_clean) > 300 else text_clean
        frontend_data["pages"].append({
            "id": page_id,
            "title": p['title'],
            "url": p['url'],
            "snippet": snippet
        })

    # Write as a js file
    output_path = os.path.join(os.path.dirname(__file__), "data.js")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("const CRAWL_DATA = ")
        json.dump(frontend_data, f, indent=2)
        f.write(";\n")
    print(f"=== Successfully exported data to {output_path} ===")


if __name__ == "__main__":
    main()
