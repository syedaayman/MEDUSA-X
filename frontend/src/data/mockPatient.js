export const demoPatient = {
  patient: {
    id: "demo-patient-001",
    name: "Alex Morgan",
    initials: "AM",
    description: "Synthetic profile · created for interface demonstration",
    documentCount: 3,
    timelineCount: 3,
  },
  timeline: [
    {
      id: "event-1",
      date: "2025-01-12",
      displayDate: "12 Jan 2025",
      title: "Example outpatient note",
      description:
        "Synthetic event used to preview chronological record presentation.",
      source: "sample-clinic-note.pdf",
      page: 1,
    },
    {
      id: "event-2",
      date: "2025-02-04",
      displayDate: "04 Feb 2025",
      title: "Example laboratory report",
      description:
        "Synthetic event used to show document date and evidence navigation.",
      source: "sample-lab-report.pdf",
      page: 2,
    },
    {
      id: "event-3",
      date: "2025-02-11",
      displayDate: "11 Feb 2025",
      title: "Example discharge note",
      description:
        "Synthetic event demonstrating a later point in the example history.",
      source: "sample-discharge-note.pdf",
      page: 1,
    },
  ],
  conflicts: [
    {
      id: "conflict-1",
      title: "Example medication discrepancy",
      description:
        "Two synthetic source excerpts show different example dosage instructions.",
      sources: ["sample-clinic-note.pdf, p. 1", "sample-discharge-note.pdf, p. 1"],
    },
  ],
  sources: [
    {
      id: "source-1",
      document: "sample-clinic-note.pdf",
      page: 1,
      excerpt: "Synthetic example: medication instruction A (illustrative text only).",
    },
    {
      id: "source-2",
      document: "sample-discharge-note.pdf",
      page: 1,
      excerpt: "Synthetic example: medication instruction B (illustrative text only).",
    },
  ],
};
