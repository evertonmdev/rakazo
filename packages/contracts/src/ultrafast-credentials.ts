import * as z from "zod";

/** Write-only. Omit a field to keep the saved key. Empty string clears it. */
export const SaveUltrafastCredentialsInput = z.object({
  botId: z.string().trim().min(1),
  typesafeApiKey: z.string().max(4096).optional(),
  textModelApiKey: z.string().max(4096).optional(),
});

export const UltrafastCredentialsStatus = z.object({
  typesafeConfigured: z.boolean(),
  textModelConfigured: z.boolean(),
});
