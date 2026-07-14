declare module "spark-md5" {
  namespace SparkMD5 {
    class ArrayBuffer {
      append(buffer: globalThis.ArrayBuffer): this;
      end(raw?: boolean): string;
      reset(): this;
    }
  }

  export = SparkMD5;
}
