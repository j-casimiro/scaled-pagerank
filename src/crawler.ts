import * as fs from 'fs';
import * as path from 'path';
import { load } from 'cheerio';

/**
 * Standard English Stop Words Set
 * Words commonly used in text that are ignored during indexing and search queries
 * to focus relevance scoring on meaningful terms.
 */
const STOP_WORDS = new Set([
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
]);

/**
 * Wikipedia namespaces and citation identifiers to blacklist.
 * This prevents authority leaks and keeps the crawl focused on content articles.
 */
const BLACKLIST_PREFIXES = [
  "wikipedia:", "file:", "help:", "category:", "special:", "talk:", "portal:",
  "template:", "template_talk:", "book:", "draft:", "module:", "mediawiki:",
  "user:", "user_talk:", "category_talk:", "special:", "wp:", "talk:",
  "isbn", "doi", "issn", "pmid", "s2cid"
];

/**
 * Standardizes Wikipedia URLs to extract a clean, normalized lower_case_title.
 * Handles decoding, replaces spaces/underscores, and strips anchors/parameters.
 * 
 * @param url Wikipedia page URL.
 */
function normalizeWikiTitle(url: string): string {
  let titlePart = url;
  if (url.includes('/wiki/')) {
    const parts = url.split('/wiki/');
    titlePart = parts[parts.length - 1];
  }
  titlePart = titlePart.split('#')[0];
  titlePart = titlePart.split('?')[0];
  titlePart = titlePart.replace(/_/g, ' ').replace(/%20/g, ' ');
  titlePart = decodeURIComponent(titlePart);
  return titlePart.trim().replace(/ /g, '_').toLowerCase();
}

interface CrawlerPage {
  url: string;
  title: string;
  text: string;
}

/**
 * A breadth-first search crawler that fetches Wikipedia articles starting from a seed URL,
 * extracts content/out-links, and constructs a closed-universe link graph.
 */
class WikiCrawler {
  private limit: number;
  private seedUrl: string;
  public pages: { [pageId: number]: CrawlerPage } = {};
  public urlToId: { [normTitle: string]: number } = {};
  private rawOutLinks: { [pageId: number]: string[] } = {};
  public adjacencyList: { [pageId: number]: number[] } = {};
  
  // Custom User-Agent header to comply with Wikipedia API guidelines
  private headers = {
    'User-Agent': 'WikiPageRankPrototype/1.0 (contact: jehubaclecasimiro@gmail.com; educational research prototype) Node-fetch/3.0'
  };

  /**
   * @param limit Maximum number of unique content pages to crawl.
   * @param seedUrl Wikipedia URL to start the BFS crawling from.
   */
  constructor(limit = 100, seedUrl = "https://en.wikipedia.org/wiki/Scientific_Revolution") {
    this.limit = limit;
    this.seedUrl = seedUrl;
  }

  /**
   * Extracts clean, space-separated body text from a Cheerio loaded DOM object.
   * Targets paragraphs in the main article body.
   */
  private extractText($: any): string {
    const contentDiv = $('#mw-content-text');
    if (!contentDiv.length) return "";
    const paragraphs: string[] = [];
    contentDiv.find('p').each((_: any, el: any) => {
      paragraphs.push($(el).text());
    });
    return paragraphs.join(" ");
  }

  /**
   * Extracts non-blacklisted internal Wikipedia links from the article body.
   * Ignores namespaces, external links, and the main page.
   */
  private extractLinks($: any): string[] {
    const links: string[] = [];
    const contentDiv = $('#mw-content-text');
    if (!contentDiv.length) return links;

    contentDiv.find('a[href]').each((_: any, el: any) => {
      const href = $(el).attr('href') || "";
      if (href.startsWith('/wiki/')) {
        const articleName = href.substring(6);
        const articleNameLower = articleName.toLowerCase();
        
        // Filter out namespaces (Category:, Special:, Talk:, templates, etc.)
        const isBlacklisted = BLACKLIST_PREFIXES.some(prefix => articleNameLower.startsWith(prefix));
        if (!isBlacklisted && articleNameLower !== "main_page") {
          const absUrl = `https://en.wikipedia.org/wiki/${articleName.split('#')[0].split('?')[0]}`;
          links.push(absUrl);
        }
      }
    });
    return Array.from(new Set(links));
  }

  /**
   * Executes the breadth-first crawler loop until the page limit is reached.
   */
  public async crawl(): Promise<{ [pageId: number]: CrawlerPage }> {
    const queue = [this.seedUrl];
    const visitedUrls = new Set<string>();

    console.log(`=== Starting Wikipedia BFS Crawler (Seed: ${this.seedUrl}, Target: ${this.limit} pages) ===`);

    while (queue.length > 0 && Object.keys(this.pages).length < this.limit) {
      const currentUrl = queue.shift()!;
      const normTitle = normalizeWikiTitle(currentUrl);

      if (normTitle in this.urlToId || visitedUrls.has(currentUrl)) {
        continue;
      }
      visitedUrls.add(currentUrl);
      
      // Politeness delay to prevent rate-limiting/IP blocks
      await new Promise(resolve => setTimeout(resolve, 150));

      try {
        const pageNum = Object.keys(this.pages).length + 1;
        console.log(`[${pageNum}/${this.limit}] Fetching: ${currentUrl} ... `);
        
        const response = await fetch(currentUrl, { headers: this.headers });
        if (response.status !== 200) {
          console.log(`Failed (HTTP ${response.status})`);
          continue;
        }

        const canonicalUrl = response.url;
        const canonicalNorm = normalizeWikiTitle(canonicalUrl);

        // Handle Wikipedia redirects gracefully
        if (canonicalNorm in this.urlToId) {
          console.log(`Redirected to already crawled article: ${canonicalUrl}`);
          this.urlToId[normTitle] = this.urlToId[canonicalNorm];
          continue;
        }

        const html = await response.text();
        const $ = load(html);
        
        const firstHeading = $('#firstHeading');
        const title = firstHeading.length 
          ? firstHeading.text() 
          : canonicalUrl.split('/wiki/').pop()!.replace(/_/g, ' ');

        const text = this.extractText($);
        if (!text.trim() || text.length < 200) {
          console.log("Skipped (insufficient main content text)");
          continue;
        }

        const outLinks = this.extractLinks($);
        const pageId = Object.keys(this.pages).length;

        // Save page details
        this.pages[pageId] = {
          url: canonicalUrl,
          title: title,
          text: text
        };
        this.urlToId[canonicalNorm] = pageId;
        this.urlToId[normTitle] = pageId;
        this.rawOutLinks[pageId] = outLinks;

        console.log(`Success! '${title}' (${outLinks.length} out-links extracted)`);

        // Queue newly discovered links
        for (const link of outLinks) {
          const linkNorm = normalizeWikiTitle(link);
          if (!(linkNorm in this.urlToId) && !visitedUrls.has(link)) {
            if (queue.length < this.limit * 5) {
              queue.push(link);
            }
          }
        }
      } catch (err) {
        console.log(`Network or parsing error: ${err}`);
      }
    }

    // Build the adjacency list. Links are constrained to the closed universe of crawled pages.
    for (const [pageIdStr, links] of Object.entries(this.rawOutLinks)) {
      const pageId = parseInt(pageIdStr);
      const targets: number[] = [];
      for (const link of links) {
        const linkNorm = normalizeWikiTitle(link);
        if (linkNorm in this.urlToId) {
          const targetId = this.urlToId[linkNorm];
          // Filter out self-loops to keep simple adjacency properties
          if (targetId !== pageId) {
            targets.push(targetId);
          }
        }
      }
      this.adjacencyList[pageId] = Array.from(new Set(targets));
    }

    console.log(`Successfully built graph. Nodes: ${Object.keys(this.pages).length}`);
    return this.pages;
  }
}

/**
 * Builds a TF-IDF inverted index over crawled pages.
 */
class WikiIndexer {
  private pages: { [pageId: number]: CrawlerPage };
  private N: number;
  public invertedIndex: { [term: string]: { [pageIdStr: string]: number } } = {};
  private docLengths: { [pageId: number]: number } = {};
  private dfs: { [term: string]: number } = {};

  /**
   * @param pages Dictionary of crawled pages mapped by page ID.
   */
  constructor(pages: { [pageId: number]: CrawlerPage }) {
    this.pages = pages;
    this.N = Object.keys(pages).length;
  }

  /**
   * Cleans, tokenizes, and filters text to return meaningful lowercase term tokens.
   */
  private cleanText(text: string): string[] {
    const cleaned = text.toLowerCase().replace(/[^\w\s]/g, ' ');
    const tokens = cleaned.split(/\s+/);
    return tokens.filter(t => !STOP_WORDS.has(t) && t.length > 1);
  }

  /**
   * Computes term frequencies (TF) and inverse document frequencies (IDF) to compile
   * the final inverted index.
   * 
   * Formulas:
   * TF(t, d) = Count(t in d) / TotalTokens(d)
   * IDF(t) = ln(N / DF(t)) + 1.0
   * TF-IDF(t, d) = TF(t, d) * IDF(t)
   */
  public buildIndex(): { [term: string]: { [pageIdStr: string]: number } } {
    console.log("=== Initializing Document Text Indexer ===");
    const docTokens: { [pageId: number]: string[] } = {};

    // First pass: tokenize and count Document Frequencies (DF)
    for (const [pageIdStr, pageData] of Object.entries(this.pages)) {
      const pageId = parseInt(pageIdStr);
      const tokens = this.cleanText(pageData.text);
      this.docLengths[pageId] = tokens.length;
      docTokens[pageId] = tokens;

      const uniqueTerms = new Set(tokens);
      for (const term of uniqueTerms) {
        this.dfs[term] = (this.dfs[term] || 0) + 1;
      }
    }

    // Second pass: compute TF-IDF values
    for (const [pageIdStr, tokens] of Object.entries(docTokens)) {
      const pageId = parseInt(pageIdStr);
      const docLen = this.docLengths[pageId];
      if (docLen === 0) continue;

      const termCounts: { [term: string]: number } = {};
      for (const token of tokens) {
        termCounts[token] = (termCounts[token] || 0) + 1;
      }

      for (const [term, count] of Object.entries(termCounts)) {
        const tf = count / docLen;
        const df = this.dfs[term];
        const idf = Math.log(this.N / df) + 1.0;
        const tfIdf = tf * idf;

        if (!(term in this.invertedIndex)) {
          this.invertedIndex[term] = {};
        }
        this.invertedIndex[term][pageIdStr] = tfIdf;
      }
    }

    console.log(`Successfully indexed ${Object.keys(this.invertedIndex).length} terms.`);
    return this.invertedIndex;
  }
}

/**
 * Main execution runner. Crawls Wikipedia, runs indexer, and writes final database
 * to data.js.
 */
async function run() {
  const crawler = new WikiCrawler(100);
  const pages = await crawler.crawl();

  const indexer = new WikiIndexer(pages);
  const invertedIndex = indexer.buildIndex();

  const frontendData = {
    pages: [] as any[],
    adjacency_list: crawler.adjacencyList,
    inverted_index: invertedIndex
  };

  // Compile snippet and export structure
  for (const [pageIdStr, p] of Object.entries(pages)) {
    const pageId = parseInt(pageIdStr);
    const cleanText = p.text.replace(/\s+/g, ' ').trim();
    const snippet = cleanText.length > 300 
      ? cleanText.substring(0, 300) + '...' 
      : cleanText;
      
    frontendData.pages.push({
      id: pageId,
      title: p.title,
      url: p.url,
      snippet: snippet
    });
  }

  const outputPath = path.join(__dirname, '..', 'dist', 'data.js');
  const fileContent = `const CRAWL_DATA = ${JSON.stringify(frontendData, null, 2)};\n`;
  fs.writeFileSync(outputPath, fileContent, 'utf-8');
  console.log(`=== Successfully exported database to: ${outputPath} ===`);
}

run();
