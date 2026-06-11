# Wikipedia PageRank & Search Engine Prototype

A small-scale prototype of the original Google search engine architecture described in the 1998 paper "The Anatomy of a Large-Scale Hypertextual Web Search Engine" by Sergey Brin and Lawrence Page.

The project crawls Wikipedia articles, calculates their PageRank, builds an inverted index, and resolves multi-word search queries. It features an interactive HTML/JS dashboard using D3.js powered by compiled TypeScript classes.

## Core Components

1. **Crawler (`src/crawler.ts`)**:
   - Performs a breadth-first crawl of Wikipedia articles starting from a seed page centered on the Scientific Revolution.
   - Implements politeness delays (150ms) and user-agent settings.
   - Filters out administrative namespaces and blacklists citation page identifiers (`ISBN`, `DOI`, `ISSN`, etc.) to prevent PageRank leaks.
   - Exports crawled data to `dist/data.js`.

2. **TF-IDF Indexer**:
   - Tokenizes, token-cleans, and filters English stop words.
   - Calculates document frequency (DF) and term frequency (TF).
   - Generates weighted TF-IDF scores for all index terms.

3. **PageRank Solver (`src/engine.ts` => `dist/engine.js`)**:
   - Computes PageRank power iterations using sink node redistribution.
   - Interacts dynamically with the dashboard to solve PageRank live when the damping factor is adjusted in the UI.

4. **Query Resolver (`src/engine.ts` => `dist/engine.js`)**:
   - Resolves search queries using either multiplicative scoring or a normalized linear combination score:
     $$\text{Score} = \text{Relevance}_{\text{norm}} + \alpha \cdot \text{PR}_{\text{norm}}$$
   - Normalizing relevance and PageRank to a $[0, 1]$ scale prevents PageRank values from drowning out TF-IDF scores.

5. **Dashboard (`index.html`)**:
   - Fully client-side dashboard loaded via `file:///` protocol. Does not require a local web server.
   - Displays the article graph using D3.js force simulation.
   - Nodes are sized dynamically based on PageRank.
   - Shows active connections (in-links in green, out-links in purple) on node select or hover.
   - Optimized for rendering performance with synchronous pre-calculation ticks on load, max charge distance constraints, and dynamic arrowhead marker toggles.

## Project Structure

```
page-rank/
├── src/
│   ├── crawler.ts          # Wikipedia crawler & indexer source (Node.js)
│   └── engine.ts           # PageRank & Search resolver source
├── dist/
│   ├── data.js             # Generated crawl database
│   └── engine.js           # Compiled search engine bundle (browser ES6)
├── package.json            # Node project configuration and dependencies
├── index.html              # Interactive HTML/CSS/JS visualization dashboard
├── README.md               # Project overview
└── pagerank_research_paper.md # Research report on metrics and findings
```

## Running the Project

### Visual Dashboard
Open `index.html` in a web browser directly or serve it locally. Use the tabs to search the dataset, inspect the graph, or view the convergence logs.

### Installation
Install dependencies:
```bash
npm install
```

### Recrawling Pages
To crawl a fresh set of pages and rebuild `dist/data.js`:
```bash
npm run crawl
```

### Rebuilding the Engine
To compile TypeScript logic into standard ES6 browser JavaScript:
```bash
npm run build
```

## Mathematical Formulation

### PageRank
$$\text{Google Matrix } M = d \cdot P + \frac{1-d}{N} \cdot E$$
$$\text{Power Iteration } R^{(t+1)} = M R^{(t)}$$
Where $P$ is the transition probability matrix, $d$ is the damping factor, $E$ is an $N \times N$ matrix of ones, and $N$ is the number of nodes. Iteration stops when $||R^{(t+1)} - R^{(t)}||_1 < 10^{-6}$.

### Search Scoring
$$\text{Score}(q, d) = \frac{\text{Relevance}(q, d)}{\max_j \text{Relevance}(q, j)} + \alpha \cdot \frac{\text{PageRank}_d}{\max_j \text{PageRank}_j}$$
Where Relevance is the sum of TF-IDF scores for query terms in document $d$, and $\alpha$ is the combination weight.
