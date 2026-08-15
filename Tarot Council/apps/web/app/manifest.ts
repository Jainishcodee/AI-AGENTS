import type { MetadataRoute } from "next";

/**
 * Installable, because of one specific job.
 *
 * "Mobile" here does not mean running a deliberation on a phone — that is 30–90 seconds
 * of six columns of tables, and it belongs on a laptop. The phone job is **recording an
 * outcome**, which happens when the outcome happens: the offer arrives, the conversation
 * goes badly, you find out who actually decided. That is a 30-second task, and if it
 * needs a desktop it does not get done — which means the corpus never accumulates and
 * Phase 3 has nothing to measure.
 *
 * So the app installs, and `/history?status=due` is a shortcut, because that is the
 * screen worth one tap.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Cognitive OS",
    short_name: "Council",
    description:
      "Six reasoning engines analyse one decision, and you record what actually happened.",
    start_url: "/",
    display: "standalone",
    background_color: "#08080a",
    theme_color: "#08080a",
    orientation: "any",
    categories: ["productivity", "utilities"],
    shortcuts: [
      {
        name: "Record an outcome",
        short_name: "Due",
        description: "Decisions whose check-in date has arrived",
        url: "/history?status=due",
      },
      { name: "Track record", short_name: "Scores", url: "/calibration" },
    ],
  };
}
