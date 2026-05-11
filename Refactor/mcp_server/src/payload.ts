export function okPayload(tool: string, url: string, data: any) {
  return {
    content: [
      { type: "text" as const, text: JSON.stringify({ ok: true, tool, url, data }, null, 2) },
    ],
  };
}

export function errPayload(tool: string, error: unknown) {
  return {
    content: [
      {
        type: "text" as const,
        text: JSON.stringify(
          { ok: false, tool, error: (error as any)?.message ?? String(error) },
          null,
          2,
        ),
      },
    ],
    isError: true,
  };
}
