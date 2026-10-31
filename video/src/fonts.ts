import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

export const fontsReady = Promise.all([
  loadFont({ family: "Corm", url: staticFile("fonts/CormorantGaramond.ttf"), style: "normal", weight: "300 700" }),
  loadFont({ family: "Corm", url: staticFile("fonts/CormorantGaramond-Italic.ttf"), style: "italic", weight: "300 700" }),
  loadFont({ family: "Inter", url: staticFile("fonts/Inter.ttf"), weight: "100 900" }),
]);
