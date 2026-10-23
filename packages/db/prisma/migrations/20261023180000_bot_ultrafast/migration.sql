-- Optional Jev Ultrafast browser loop. Default page tools stay unchanged.
ALTER TABLE "bots" ADD COLUMN "ultrafastEnabled" BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE "bots" ADD COLUMN "ultrafastTypesafeSecretId" TEXT;
ALTER TABLE "bots" ADD COLUMN "ultrafastTextModelSecretId" TEXT;
