# Wikipedia PageRank & Search Engine Prototype

A small-scale prototype of the original Google search engine architecture described in the 1998 paper "The Anatomy of a Large-Scale Hypertextual Web Search Engine" by Sergey Brin and Lawrence Page.

The project crawls Wikipedia articles, calculates their PageRank, builds an inverted index, and resolves multi-word search queries. It includes an interactive HTML/JS dashboard using D3.js.

## Core Components

1. **Crawler (`export_data.py`)**:
   - Performs a breadth-first crawl of Wikipedia articles starting from a seed page (default: `/wiki/History`).
   - Implements politeness delays (150ms) and user-agent settings.
   - Filters out administrative namespaces and blacklists citation page identifiers (`ISBN`, `DOI`, `ISSN`, etc.) to prevent PageRank leaks.
   - Exports crawled data to `data.js`.

2. **TF-IDF Indexer**:
   - Tokenizes, token-cleans, and filters English stop words.
   - Calculates document frequency (DF) and term frequency (TF).
   - Generates weighted TF-IDF scores for all index terms.

3. **Dashboard (`index.html`)**:
   - Fully client-side dashboard loaded via `file:///` protocol. Does not require a local web server.
   - Computes PageRank power iterations in JavaScript when the damping factor is adjusted.
   - Displays the article graph using D3.js force simulation.
   - Nodes are sized dynamically based on PageRank.
   - Shows active connections (in-links in green, out-links in purple) on node select or hover.
   - Optimized for rendering performance with synchronous pre-calculation ticks on load, max charge distance constraints, and dynamic arrowhead marker toggles.

4. **Query Resolver**:
   - Resolves search queries using either multiplicative scoring or a normalized linear combination score:
     $$\text{Score} = \text{Relevance}_{\text{norm}} + \alpha \cdot \text{PR}_{\text{norm}}$$
   - Normalizing relevance and PageRank to a $[0, 1]$ scale prevents PageRank values from drowning out TF-IDF scores.

## Project Structure

```
page-rank/
├── export_data.py          # Crawler, indexer, and data exporter script
├── index.html              # HTML/CSS/JS visualization dashboard
├── data.js                 # Exported crawled data database
├── search_engine.py        # Terminal-only CLI Python prototype
└── pagerank_research_paper.md # Research report on metrics and findings
```

## Running the Project

### Visual Dashboard
Open `index.html` in a web browser. Use the tabs to search the dataset, inspect the graph, or view the convergence logs.

### Recrawling Pages
To crawl a fresh set of pages and rebuild `data.js`:
1. Install requirements:
   ```bash
   pip install requests beautifulsoup4
   ```
2. Run the exporter script:
   ```bash
   python3 export_data.py
   ```
3. Refresh `index.html` in the browser.

## Mathematical Formulation

### PageRank
$$\text{Google Matrix } M = d \cdot P + \frac{1-d}{N} \cdot E$$
$$\text{Power Iteration } R^{(t+1)} = M R^{(t)}$$
Where $P$ is the transition probability matrix, $d$ is the damping factor, $E$ is an $N \times N$ matrix of ones, and $N$ is the number of nodes. Iteration stops when $||R^{(t+1)} - R^{(t)}||_1 < 10^{-6}$.

### Search Scoring
$$\text{Score}(q, d) = \frac{\text{Relevance}(q, d)}{\max_j \text{Relevance}(q, j)} + \alpha \cdot \frac{\text{PageRank}_d}{\max_j \text{PageRank}_j}$$
Where Relevance is the sum of TF-IDF scores for query terms in document $d$, and $\alpha$ is the combination weight.
