import SparkMD5 from "spark-md5";

const HASH_CHUNK_SIZE_BYTES = 2 * 1024 * 1024;

export async function calculateFileMd5(
  file: File,
  onProgress?: (progressPercent: number) => void,
): Promise<string> {
  const spark = new SparkMD5.ArrayBuffer();
  const totalChunks = Math.max(1, Math.ceil(file.size / HASH_CHUNK_SIZE_BYTES));

  for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
    const start = chunkIndex * HASH_CHUNK_SIZE_BYTES;
    const end = Math.min(start + HASH_CHUNK_SIZE_BYTES, file.size);
    const buffer = await file.slice(start, end).arrayBuffer();
    spark.append(buffer);
    onProgress?.(Math.round(((chunkIndex + 1) / totalChunks) * 100));
  }

  return spark.end();
}
