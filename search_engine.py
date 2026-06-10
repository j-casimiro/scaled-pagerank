#!/usr/bin/env python3
"""
Wikipedia PageRank Search Engine Prototype
Based on the 1998 paper:
"The Anatomy of a Large-Scale Hypertextual Web Search Engine" by Sergey Brin and Lawrence Page.

This script implements:
1. A Mini-Crawler that crawls 100 Wikipedia pages starting from a seed page.
2. A PageRank Calculator using the power iteration method on transition probability matrices.
3. An Indexer that builds an inverted index using TF-IDF.
4. A Search Resolver that ranks pages using combined TF-IDF and PageRank scores.
"""

import sys
import time
import re
import math
import urllib.parse
import requests
from bs4 import BeautifulSoup
import numpy as np

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

# Wikipedia namespaces and pages to skip
BLACKLIST_PREFIXES = (
    "wikipedia:", "file:", "help:", "category:", "special:", "talk:", "portal:",
    "template:", "template_talk:", "book:", "draft:", "module:", "mediawiki:",
    "user:", "user_talk:", "category_talk:", "special:", "wp:", "talk:"
)


def normalize_wiki_title(url):
    """
    Extracts and normalizes the Wikipedia page identifier from a URL.
    This resolves issues with different casing, spaces vs underscores, and relative links.
    """
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
    """
    Crawls a specified number of Wikipedia pages starting from a seed URL.
    Restricts the crawl to valid article pages and builds a closed-universe graph.
    """
    def __init__(self, limit=100, seed_url="https://en.wikipedia.org/wiki/History"):
        self.limit = limit
        self.seed_url = seed_url
        self.pages = {}            # page_id -> {'url': url, 'title': title, 'text': text}
        self.url_to_id = {}        # normalized_title -> page_id
        self.raw_out_links = {}    # page_id -> list of raw out-link URLs
        self.adjacency_list = {}   # page_id -> list of target page_ids within the universe
        self.headers = {
            'User-Agent': 'WikiPageRankPrototype/1.0 (contact: jehu@example.com; educational research prototype) Python-requests/2.0'
        }

    def _extract_text(self, soup):
        """Extracts text content only from main body paragraphs to avoid noise."""
        content_div = soup.find('div', id='mw-content-text')
        if not content_div:
            return ""
        # Only grab text from paragraphs in the main article body
        paragraphs = content_div.find_all('p')
        return " ".join([p.get_text() for p in paragraphs])

    def _extract_links(self, soup):
        """Extracts valid wiki article links from the page content."""
        links = []
        content_div = soup.find('div', id='mw-content-text')
        if not content_div:
            return links

        for a in content_div.find_all('a', href=True):
            href = a['href']
            # We only want internal wiki links
            if href.startswith('/wiki/'):
                # Exclude namespace metadata pages
                article_name = href[6:]  # Strip '/wiki/'
                article_name_lower = article_name.lower()
                if any(article_name_lower.startswith(prefix) for prefix in BLACKLIST_PREFIXES):
                    continue
                if article_name_lower == "main_page":
                    continue

                abs_url = f"https://en.wikipedia.org{href.split('#')[0].split('?')[0]}"
                links.append(abs_url)
        return list(set(links))  # Deduplicate links on the same page

    def crawl(self):
        queue = [self.seed_url]
        visited_urls = set()  # To track what we've queued or fetched

        print(f"=== Starting Crawl (Seed: {self.seed_url}, Target: {self.limit} pages) ===")

        while queue and len(self.pages) < self.limit:
            current_url = queue.pop(0)
            norm_title = normalize_wiki_title(current_url)

            # Skip if we already queued/visited this URL
            if norm_title in self.url_to_id:
                continue
            if current_url in visited_urls:
                continue
            visited_urls.add(current_url)

            # Politeness delay to respect Wikipedia servers
            time.sleep(0.15)

            try:
                print(f"[{len(self.pages) + 1}/{self.limit}] Fetching: {current_url} ... ", end="", flush=True)
                response = requests.get(current_url, headers=self.headers, timeout=5)
                if response.status_code != 200:
                    print(f"Failed (HTTP {response.status_code})")
                    continue

                canonical_url = response.url
                canonical_norm = normalize_wiki_title(canonical_url)

                # If redirected to an already crawled page
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

                # Assign ID and store page data
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

                # Queue new links
                for link in out_links:
                    link_norm = normalize_wiki_title(link)
                    if link_norm not in self.url_to_id and link not in visited_urls:
                        # Limit queue size to avoid excessive memory consumption
                        if len(queue) < self.limit * 5:
                            queue.append(link)

            except Exception as e:
                print(f"Error: {e}")

        # Construct adjacency list in our closed universe
        print("\n=== Constructing Graph Adjacency List ===")
        for page_id, links in self.raw_out_links.items():
            targets = []
            for link in links:
                link_norm = normalize_wiki_title(link)
                if link_norm in self.url_to_id:
                    target_id = self.url_to_id[link_norm]
                    if target_id != page_id:  # Exclude self-loops
                        targets.append(target_id)
            self.adjacency_list[page_id] = list(set(targets))

        print(f"Successfully built graph of {len(self.pages)} pages.\n")
        return self.pages, self.adjacency_list


class PageRankCalculator:
    """
    Computes PageRank vector for the crawled Wikipedia page graph.
    Uses power iteration on a transition probability matrix.
    Handles sink pages (pages with no outgoing links) by distributing probability evenly.
    """
    def __init__(self, adjacency_list, num_pages):
        self.adjacency_list = adjacency_list
        self.N = num_pages

    def calculate(self, d=0.85, max_iterations=1000, tolerance=1e-6):
        print("=== Computing PageRank ===")
        
        # 1. Initialize the transition probability matrix P
        # P[i, j] is the transition probability from page j to page i
        P = np.zeros((self.N, self.N))
        
        for u in range(self.N):
            targets = self.adjacency_list.get(u, [])
            if not targets:
                # Sink node: transition to all nodes with equal probability
                P[:, u] = 1.0 / self.N
            else:
                # Distribute probability evenly among outgoing links
                prob = 1.0 / len(targets)
                for v in targets:
                    P[v, u] = prob

        # 2. Build the Google Matrix M
        # M = d * P + ((1 - d) / N) * E, where E is an N x N matrix of ones.
        M = d * P + ((1.0 - d) / self.N) * np.ones((self.N, self.N))

        # 3. Power Iteration
        # R is initialized to a uniform vector
        R = np.ones(self.N) / self.N
        
        converged = False
        for i in range(max_iterations):
            R_next = np.dot(M, R)
            
            # Check convergence using L1 Norm (Manhattan distance)
            diff = np.sum(np.abs(R_next - R))
            if diff < tolerance:
                R = R_next
                converged = True
                print(f"Convergence achieved in {i+1} iterations (L1 delta: {diff:.3e}).")
                break
            R = R_next

        if not converged:
            print(f"Warning: Power iteration did not converge within {max_iterations} iterations.")

        # Ensure the PageRank vector sums to 1.0
        sum_pr = np.sum(R)
        print(f"Sum of PageRank scores: {sum_pr:.6f}")
        return R


class WikiIndexer:
    """
    Cleans raw text, tokenizes, removes stop words, and builds
    both forward and inverted indexes with TF-IDF weighting.
    """
    def __init__(self, pages):
        self.pages = pages
        self.N = len(pages)
        self.inverted_index = {}  # term -> {page_id -> tf_idf}
        self.doc_lengths = {}     # page_id -> word count (after cleaning)
        self.dfs = {}             # term -> number of documents containing it

    def _clean_text(self, text):
        """Tokenizes text, strips punctuation, lowercases, and removes stop words."""
        text = text.lower()
        # Replace non-alphanumeric characters with spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.split()
        # Filter stop words and single characters
        return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]

    def build_index(self):
        print("=== Indexing Pages & Calculating TF-IDF ===")
        # Map to store preprocessed tokens for each document
        doc_tokens = {}

        # Step 1: Calculate term counts and Document Frequency (DF)
        for page_id, page_data in self.pages.items():
            tokens = self._clean_text(page_data['text'])
            self.doc_lengths[page_id] = len(tokens)
            doc_tokens[page_id] = tokens

            unique_terms = set(tokens)
            for term in unique_terms:
                self.dfs[term] = self.dfs.get(term, 0) + 1

        # Step 2: Compute TF-IDF scores and populate inverted index
        for page_id, tokens in doc_tokens.items():
            doc_len = self.doc_lengths[page_id]
            if doc_len == 0:
                continue

            # Count local term occurrences
            term_counts = {}
            for token in tokens:
                term_counts[token] = term_counts.get(token, 0) + 1

            for term, count in term_counts.items():
                tf = count / doc_len
                df = self.dfs[term]
                # Inverse Document Frequency with +1 smoothing
                idf = math.log(self.N / df) + 1.0
                tf_idf = tf * idf

                if term not in self.inverted_index:
                    self.inverted_index[term] = {}
                self.inverted_index[term][page_id] = tf_idf

        print(f"Indexed {len(self.inverted_index)} unique terms across {self.N} documents.\n")
        return self.inverted_index


class SearchResolver:
    """
    Resolves user search queries. Combines content relevance (TF-IDF)
    and link authority (PageRank) to score matching documents.
    """
    def __init__(self, inverted_index, pageranks, pages):
        self.inverted_index = inverted_index
        self.pageranks = pageranks
        self.pages = pages

    def _clean_query(self, query):
        """Applies same cleaning pipeline to the query."""
        query = query.lower()
        query = re.sub(r'[^\w\s]', ' ', query)
        tokens = query.split()
        return [t for t in tokens if t not in STOP_WORDS]

    def search(self, query, alpha=5.0):
        query_terms = self._clean_query(query)
        print(f"Query terms searched: {query_terms}")
        if not query_terms:
            return []

        # Find matching documents and sum TF-IDF scores
        doc_relevance = {}
        matched_terms_per_doc = {}

        for term in query_terms:
            if term in self.inverted_index:
                for page_id, tf_idf in self.inverted_index[term].items():
                    doc_relevance[page_id] = doc_relevance.get(page_id, 0.0) + tf_idf
                    if page_id not in matched_terms_per_doc:
                        matched_terms_per_doc[page_id] = []
                    matched_terms_per_doc[page_id].append(term)

        results = []
        for page_id, relevance in doc_relevance.items():
            pr = self.pageranks[page_id]
            
            # Method 1: Strict Multiplicative Score (Original requirement)
            score_mul = relevance * pr

            # Method 2: Log-Linear Combination (Handles scale differences)
            # Score = Relevance + alpha * log(PageRank)
            # Since PageRank is a probability (0 < pr < 1), log(pr) is negative.
            # Adding a constant shift ensures positive values for visualization.
            score_log_linear = relevance + alpha * (math.log(pr) + 10.0)

            results.append({
                'id': page_id,
                'title': self.pages[page_id]['title'],
                'url': self.pages[page_id]['url'],
                'relevance': relevance,
                'pagerank': pr,
                'score_mul': score_mul,
                'score_log_linear': score_log_linear,
                'matched_terms': matched_terms_per_doc[page_id]
            })

        return results


def run_demo():
    print("==========================================================")
    # 1. Crawl
    # Seed page is set to 'History', crawl exactly 100 pages
    crawler = WikiCrawler(limit=100, seed_url="https://en.wikipedia.org/wiki/History")
    pages, adjacency_list = crawler.crawl()

    if len(pages) < 100:
        print(f"Warning: Only crawled {len(pages)} pages. Continuing with what was fetched.")

    # 2. Compute PageRanks
    calculator = PageRankCalculator(adjacency_list, len(pages))
    
    print("\nCalculating PageRank for d=0.85 (Standard Damping Factor)...")
    pageranks_85 = calculator.calculate(d=0.85)
    
    print("\nCalculating PageRank for d=0.50 (Lowered Damping Factor)...")
    pageranks_50 = calculator.calculate(d=0.50)

    # Print top 5 most authoritative pages under both models
    top_indices_85 = np.argsort(pageranks_85)[::-1]
    top_indices_50 = np.argsort(pageranks_50)[::-1]
    
    print("\n=== TOP 5 MOST AUTHORITATIVE PAGES (d=0.85) ===")
    for rank, idx in enumerate(top_indices_85[:5], 1):
        print(f"{rank}. {pages[idx]['title']} (ID: {idx}) | PageRank: {pageranks_85[idx]:.6f}")
        
    print("\n=== TOP 5 MOST AUTHORITATIVE PAGES (d=0.50) ===")
    for rank, idx in enumerate(top_indices_50[:5], 1):
        print(f"{rank}. {pages[idx]['title']} (ID: {idx}) | PageRank: {pageranks_50[idx]:.6f}")

    # 3. Index
    indexer = WikiIndexer(pages)
    inverted_index = indexer.build_index()

    # 4. Search Resolvers
    resolver_85 = SearchResolver(inverted_index, pageranks_85, pages)
    resolver_50 = SearchResolver(inverted_index, pageranks_50, pages)
    
    sample_queries = [
        "Roman Emperor",
        "French Revolution",
        "industrial civilization"
    ]

    print("\n==========================================================")
    print("=== RUNNING SEARCH QUERY EXPERIMENTS ===")
    print("==========================================================")

    for query in sample_queries:
        print(f"\n==================== QUERY: '{query}' ====================")
        
        # Resolve using d=0.85
        results_85 = resolver_85.search(query, alpha=5.0)
        # Resolve using d=0.50
        results_50 = resolver_50.search(query, alpha=5.0)
        
        if not results_85:
            print("No matching pages found.")
            continue

        # Helper to compute custom log-linear scores on the fly
        def get_log_linear_score(res, alpha):
            return res['relevance'] + alpha * (math.log(res['pagerank']) + 10.0)

        # ----------------------------------------------------
        # Experiment 1: Multiplicative scoring comparison
        # ----------------------------------------------------
        print("\n--- [Multiplicative Score: Relevance * PageRank] ---")
        
        # d=0.85
        results_85.sort(key=lambda x: x['score_mul'], reverse=True)
        print("  [Model A: d=0.85]")
        for rank, res in enumerate(results_85[:3], 1):
            print(f"    {rank}. {res['title']} (Score: {res['score_mul']:.2e}, Relevance: {res['relevance']:.4f}, PR: {res['pagerank']:.4f})")
            
        # d=0.50
        results_50.sort(key=lambda x: x['score_mul'], reverse=True)
        print("  [Model B: d=0.50]")
        for rank, res in enumerate(results_50[:3], 1):
            print(f"    {rank}. {res['title']} (Score: {res['score_mul']:.2e}, Relevance: {res['relevance']:.4f}, PR: {res['pagerank']:.4f})")

        # ----------------------------------------------------
        # Experiment 2: Log-Linear scoring comparison
        # ----------------------------------------------------
        print("\n--- [Log-Linear Score: Relevance + alpha * (log(PR) + 10)] ---")
        
        # Config 1: d=0.85, alpha=5.0 (Baseline)
        results_85.sort(key=lambda x: get_log_linear_score(x, 5.0), reverse=True)
        print("  [Config 1: d=0.85, alpha=5.0 (Baseline)]")
        for rank, res in enumerate(results_85[:3], 1):
            score = get_log_linear_score(res, 5.0)
            print(f"    {rank}. {res['title']} (Score: {score:.4f}, Relevance: {res['relevance']:.4f}, PR: {res['pagerank']:.4f})")
            
        # Config 2: d=0.85, alpha=1.0 (Lowered alpha)
        results_85.sort(key=lambda x: get_log_linear_score(x, 1.0), reverse=True)
        print("  [Config 2: d=0.85, alpha=1.0 (Lowered alpha)]")
        for rank, res in enumerate(results_85[:3], 1):
            score = get_log_linear_score(res, 1.0)
            print(f"    {rank}. {res['title']} (Score: {score:.4f}, Relevance: {res['relevance']:.4f}, PR: {res['pagerank']:.4f})")
            
        # Config 3: d=0.50, alpha=1.0 (Lowered d + lowered alpha)
        results_50.sort(key=lambda x: get_log_linear_score(x, 1.0), reverse=True)
        print("  [Config 3: d=0.50, alpha=1.0 (Lowered d + lowered alpha)]")
        for rank, res in enumerate(results_50[:3], 1):
            score = get_log_linear_score(res, 1.0)
            print(f"    {rank}. {res['title']} (Score: {score:.4f}, Relevance: {res['relevance']:.4f}, PR: {res['pagerank']:.4f})")
            
        print("-" * 60)


if __name__ == "__main__":
    run_demo()

