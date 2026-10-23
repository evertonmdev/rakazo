import type { AdapterContext, SecretStore } from "@rakazo/adapter-kit";
import { persistPreparedSecret } from "./secret-persistence.js";
import type { PrismaClient } from "@rakazo/db";

export type UltrafastKeyName = "typesafe" | "text-model";

const secretField = {
  typesafe: "ultrafastTypesafeSecretId",
  "text-model": "ultrafastTextModelSecretId",
} as const;

export async function ultrafastCredentialStatus(
  prisma: PrismaClient,
  scope: { userId: string; spaceId: string; botId: string },
) {
  const bot = await prisma.bot.findFirst({
    where: { id: scope.botId, userId: scope.userId, spaceId: scope.spaceId },
    select: { ultrafastTypesafeSecretId: true, ultrafastTextModelSecretId: true },
  });
  if (!bot) return null;
  return {
    typesafeConfigured: Boolean(bot.ultrafastTypesafeSecretId),
    textModelConfigured: Boolean(bot.ultrafastTextModelSecretId),
  };
}

async function writeKey(
  prisma: PrismaClient,
  secrets: SecretStore,
  context: AdapterContext,
  botId: string,
  name: UltrafastKeyName,
  value: string,
) {
  const field = secretField[name];
  const trimmed = value.trim();
  const existing = await prisma.bot.findFirst({
    where: { id: botId, userId: context.userId, spaceId: context.spaceId },
    select: { ultrafastTypesafeSecretId: true, ultrafastTextModelSecretId: true },
  });
  if (!existing) throw new Error("Bot not found");
  if (!trimmed) {
    await prisma.bot.update({
      where: { id: botId },
      data: { [field]: null },
    });
    return;
  }
  const stored = await secrets.put(trimmed, context, { recordId: `ultrafast:${botId}:${name}` });
  await persistPreparedSecret(prisma, secrets, stored, () =>
    prisma.$transaction(async (tx) => {
      await tx.secret.create({
        data: {
          id: stored.id,
          userId: context.userId,
          spaceId: context.spaceId,
          kind: `ultrafast-${name}`,
          ciphertext: stored.ciphertext,
        },
      });
      await tx.bot.update({
        where: { id: botId },
        data: { [field]: stored.id },
      });
    }),
  );
}

export async function saveUltrafastCredentials(
  prisma: PrismaClient,
  secrets: SecretStore,
  context: AdapterContext,
  input: { botId: string; typesafeApiKey?: string; textModelApiKey?: string },
) {
  if (input.typesafeApiKey !== undefined) {
    await writeKey(prisma, secrets, context, input.botId, "typesafe", input.typesafeApiKey);
  }
  if (input.textModelApiKey !== undefined) {
    await writeKey(prisma, secrets, context, input.botId, "text-model", input.textModelApiKey);
  }
}

export async function loadUltrafastCredentials(
  prisma: PrismaClient,
  secrets: SecretStore,
  botId: string,
): Promise<{ typesafeApiKey?: string; textModelApiKey?: string }> {
  const bot = await prisma.bot.findFirst({
    where: { id: botId },
    select: { ultrafastTypesafeSecretId: true, ultrafastTextModelSecretId: true },
  });
  if (!bot) return {};
  async function read(secretId: string | null) {
    if (!secretId) return undefined;
    const row = await prisma.secret.findUnique({
      where: { id: secretId },
      select: { ciphertext: true },
    });
    if (!row) return undefined;
    return secrets.load(row.ciphertext, secretId);
  }
  const [typesafeApiKey, textModelApiKey] = await Promise.all([
    read(bot.ultrafastTypesafeSecretId),
    read(bot.ultrafastTextModelSecretId),
  ]);
  return {
    ...(typesafeApiKey ? { typesafeApiKey } : {}),
    ...(textModelApiKey ? { textModelApiKey } : {}),
  };
}
