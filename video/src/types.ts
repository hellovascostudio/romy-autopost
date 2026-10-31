export type Line = {
  text: string;
  start: number; // seconds
  end: number;
  words: number[]; // start time (s) of every space-separated token
  page: number;
  key?: boolean;
};

export type PageProps = {
  book: string;
  author: string;
  hook: string;
  hookEnd: number;
  endStart: number;
  total: number;
  lines: Line[];
  pages: number;
  pageStarts: number[];
  rings: [number, number][];
  cover: string; // file in public/
  end: { kicker?: string; title?: string; body?: string };
  handle: string;
};
