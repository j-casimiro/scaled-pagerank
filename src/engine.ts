/**
 * Wikipedia PageRank & TF-IDF Search Engine
 * 
 * This module contains client-side solvers for:
 * 1. PageRank calculation via Power Iteration.
 * 2. Search query resolution combining TF-IDF content relevance and PageRank authority.
 */

interface CrawlerPage {
  id: number;
  title: string;
  url: string;
  snippet: string;
}

interface AdjacencyList {
  [pageId: string]: number[];
}

interface InvertedIndex {
  [term: string]: {
    [pageId: string]: number;
  };
}

interface SearchResult {
  id: number;
  title: string;
  url: string;
  snippet: string;
  relevance: number;
  pagerank: number;
  score_mul: number;
  score_linear_comb: number;
  matched_terms: string[];
}

/**
 * Solves the PageRank vector over a directed graph.
 * Uses power iteration with sink distribution and damping factor.
 */
class PageRankSolver {
  private numNodes: number;
  private adjacencyList: AdjacencyList;
  public inDegreeList: { [pageId: number]: number[] } = {};

  /**
   * @param numNodes Total number of nodes in the graph universe.
   * @param adjacencyList Adjacency list mapping source node ID to target node IDs.
   */
  constructor(numNodes: number, adjacencyList: AdjacencyList) {
    this.numNodes = numNodes;
    this.adjacencyList = adjacencyList;
    this.initInDegrees();
  }

  /**
   * Constructs the in-degree list mapping target node ID to an array of incoming parent IDs.
   * Used for efficient computation of incoming rank during power iteration.
   */
  private initInDegrees(): void {
    this.inDegreeList = {};
    for (let i = 0; i < this.numNodes; i++) {
      this.inDegreeList[i] = [];
    }
    for (let u = 0; u < this.numNodes; u++) {
      const targets = this.adjacencyList[u] || [];
      for (const v of targets) {
        if (this.inDegreeList[v]) {
          this.inDegreeList[v].push(u);
        }
      }
    }
  }

  /**
   * Solves the PageRank equation: R = d * P * R + (1-d) * E * R
   * via Power Iteration (based on the original 1998 Brin & Page paper formulation).
   * 
   * In this original formulation:
   * - PageRank values sum to N (the total number of nodes) rather than 1.
   * - The initial PageRank vector is set uniformly to 1.0 for each node.
   * - Teleportation constant probability is (1 - d) instead of (1 - d) / N.
   * 
   * Handling Sinks:
   * Sink nodes are assumed to point to all pages in the parameter database.
   * 
   * @param d Damping factor (typically 0.85).
   * @param tolerance L1 convergence delta threshold.
   * @param maxIterations Safety limit for power iteration loop.
   */
  public solve(d: number, tolerance = 1e-6, maxIterations = 200): { pagerank: number[]; log: string[]; iterations: number } {
    const log: string[] = [];
    const outDegrees = new Array(this.numNodes).fill(0);
    const sinks: number[] = [];

    // Classify nodes by out-degree
    for (let u = 0; u < this.numNodes; u++) {
      outDegrees[u] = (this.adjacencyList[u] || []).length;
      if (outDegrees[u] === 0) {
        sinks.push(u);
      }
    }

    // Initialize PageRank vector uniformly to 1.0 (Sum of vector = N)
    let R = new Array(this.numNodes).fill(1.0);
    let iterations = 0;

    log.push(`Initial R_0 = 1.00000 (Sum = ${this.numNodes})`);
    log.push(`Damping factor d = ${d.toFixed(2)} (Original Teleportation constant = ${(1.0 - d).toFixed(2)})`);
    log.push(`Identified ${sinks.length} sink nodes. Redistributing their rank uniformly.`);

    // Power Iteration Loop
    for (let iter = 0; iter < maxIterations; iter++) {
      iterations++;
      let R_next = new Array(this.numNodes).fill(0);

      // Sum rank of all sink nodes
      let sinkSum = 0;
      for (const sink of sinks) {
        sinkSum += R[sink];
      }

      // Base probability in the original paper's formulation (summing to N):
      // (1 - d) + d * sinkSum / N
      const baseSurferProb = (1.0 - d) + (d * sinkSum) / this.numNodes;

      // Compute next iteration rank for each node
      for (let i = 0; i < this.numNodes; i++) {
        let incomingSum = 0;
        const parents = this.inDegreeList[i] || [];
        for (const p of parents) {
          incomingSum += R[p] / outDegrees[p];
        }
        R_next[i] = baseSurferProb + d * incomingSum;
      }

      // Calculate L1 Norm delta (absolute sum of changes)
      let diff = 0;
      for (let i = 0; i < this.numNodes; i++) {
        diff += Math.abs(R_next[i] - R[i]);
      }

      R = R_next;
      log.push(`Iteration ${iter + 1}: L1 Delta = ${diff.toExponential(4)}`);

      // Convergence check (scaled by N to maintain equivalent precision)
      const scaledTolerance = tolerance * this.numNodes;
      if (diff < scaledTolerance) {
        log.push(`Converged successfully at iteration ${iter + 1} (Delta < ${scaledTolerance.toExponential(0)})`);
        break;
      }
    }

    return { pagerank: R, log, iterations };
  }
}

/**
 * Resolves search queries by mapping query terms to indexed TF-IDF scores,
 * combining them with PageRank authority, and sorting the results.
 */
class SearchResolver {
  private pages: CrawlerPage[];
  private invertedIndex: InvertedIndex;
  private stopWords: Set<string>;

  /**
   * @param pages List of crawler page documents.
   * @param invertedIndex Mapping of terms to document TF-IDF scores.
   * @param stopWords Set of words to exclude from query analysis.
   */
  constructor(pages: CrawlerPage[], invertedIndex: InvertedIndex, stopWords: Set<string>) {
    this.pages = pages;
    this.invertedIndex = invertedIndex;
    this.stopWords = stopWords;
  }

  /**
   * Performs search query resolution.
   * 
   * Scoring Formulas:
   * 1. Multiplicative: Score = TF-IDF * PageRank
   * 2. Linear Combination: Score = Relevance_norm + alpha * PageRank_norm
   *    where values are normalized by their respective maximum candidate values.
   * 
   * @param query Raw user search input.
   * @param pagerankVector Computed PageRank values for all nodes.
   * @param alpha Weight factor for PageRank authority in linear combination mode.
   * @param mode Formula mode: 'multiplicative' or 'linear-combination'.
   */
  public search(
    query: string,
    pagerankVector: number[],
    alpha: number,
    mode: 'multiplicative' | 'linear-combination'
  ): SearchResult[] {
    // Standardize query terms and filter out stop words and short letters
    const cleanTerms = query.toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .split(/\s+/)
      .filter(t => !this.stopWords.has(t) && t.length > 1);

    if (cleanTerms.length === 0) {
      return [];
    }

    const docRelevance: { [pageId: number]: number } = {};
    const matchedTerms: { [pageId: number]: string[] } = {};

    // Sum TF-IDF scores for matching documents
    for (const term of cleanTerms) {
      if (this.invertedIndex[term]) {
        for (const [pageIdStr, tfIdf] of Object.entries(this.invertedIndex[term])) {
          const pageId = parseInt(pageIdStr);
          docRelevance[pageId] = (docRelevance[pageId] || 0) + tfIdf;
          if (!matchedTerms[pageId]) {
            matchedTerms[pageId] = [];
          }
          if (!matchedTerms[pageId].includes(term)) {
            matchedTerms[pageId].push(term);
          }
        }
      }
    }

    const results: SearchResult[] = [];
    let maxRel = 0;
    let maxPR = 0;

    // Build raw search result models
    for (const [pageIdStr, relevance] of Object.entries(docRelevance)) {
      const pageId = parseInt(pageIdStr);
      const pr = pagerankVector[pageId] || 0;
      if (relevance > maxRel) maxRel = relevance;
      if (pr > maxPR) maxPR = pr;

      results.push({
        id: pageId,
        title: this.pages[pageId].title,
        url: this.pages[pageId].url,
        snippet: this.pages[pageId].snippet,
        relevance: relevance,
        pagerank: pr,
        score_mul: 0,
        score_linear_comb: 0,
        matched_terms: matchedTerms[pageId] || []
      });
    }

    // Compute final combination scores
    results.forEach(res => {
      const rel_norm = maxRel > 0 ? res.relevance / maxRel : 0;
      const pr_norm = maxPR > 0 ? res.pagerank / maxPR : 0;

      res.score_mul = res.relevance * res.pagerank;
      res.score_linear_comb = rel_norm + alpha * pr_norm;
    });

    // Sort descending by selected ranking score
    if (mode === 'multiplicative') {
      results.sort((a, b) => b.score_mul - a.score_mul);
    } else {
      results.sort((a, b) => b.score_linear_comb - a.score_linear_comb);
    }

    return results;
  }
}

// Bind solver and resolver classes globally to window namespace for D3 dashboard access
(window as any).PageRankSolver = PageRankSolver;
(window as any).SearchResolver = SearchResolver;
