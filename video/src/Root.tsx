import { CalculateMetadataFunction, Composition } from "remotion";
import { BookPage } from "./BookPage";
import type { PageProps } from "./types";

const calculateMetadata: CalculateMetadataFunction<PageProps> = ({ props }) => ({
  durationInFrames: Math.ceil(props.total * 30),
});

const sample: PageProps = {
  book: "Rerouted for Christmas",
  author: "Romy Calloway",
  hook: "Two weeks left. One impossible itinerary.",
  hookEnd: 3,
  endStart: 12,
  total: 16,
  pages: 1,
  pageStarts: [3],
  rings: [],
  cover: "cover.jpg",
  handle: "@romycallowaywrites",
  end: { kicker: "Out now", title: "Rerouted for Christmas", body: "Kindle & paperback\nLink in bio" },
  lines: [
    { text: "And below it:", start: 3.2, end: 4.4, words: [3.2, 3.6, 4.0], page: 0 },
    {
      text: "Forty-eight hours to get her boss home.", start: 5, end: 8,
      words: [5, 5.3, 5.7, 6.1, 6.6, 6.9, 7.1, 7.4], page: 0, key: true,
    },
  ],
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="BookPage"
    component={BookPage}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={480}
    defaultProps={sample}
    calculateMetadata={calculateMetadata}
  />
);
