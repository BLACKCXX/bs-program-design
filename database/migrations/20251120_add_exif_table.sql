-- 20251120_add_exif_table.sql
-- 一图一条 EXIF 记录的独立表
-- 说明：
--   - image_id 同时为 PK & FK → images(id)
--   - 其他字段大致参考《引言》中 4.2.3 EXIF 表设计
--   - 与现有 images 表中的 camera_* / taken_at / gps_* 字段配合使用

-- 这里假设已经通过命令行指定了数据库（docker compose 那条命令会传 "$MYSQL_DATABASE"），
-- 所以本脚本里不再写 USE xxx;

-- 1) 创建 exif 表（如不存在）
CREATE TABLE IF NOT EXISTS exif (
  image_id     INT NOT NULL,                -- 对应 images.id，一图一条
  camera_make  VARCHAR(64) NULL,            -- 相机品牌
  camera_model VARCHAR(64) NULL,            -- 相机型号
  f_number     DECIMAL(5,2) NULL,           -- 光圈 F 值，例如 2.80
  exposure_time VARCHAR(16) NULL,           -- 曝光时间，字符串形式，如 '1/125'
  iso          INT NULL,                    -- 感光度
  focal_length DECIMAL(5,2) NULL,           -- 焦距（mm）

  taken_at     DATETIME NULL COMMENT '拍摄时间',
  gps_lat      DECIMAL(10,7) NULL,          -- 纬度
  gps_lng      DECIMAL(10,7) NULL,          -- 经度

  extra        JSON NULL COMMENT '其他厂商扩展 EXIF，原始字典或部分字段',
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (image_id),
  CONSTRAINT fk_exif_image
    FOREIGN KEY (image_id) REFERENCES images(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) 将已有 images 表中的 EXIF 字段同步一份到 exif 表
-- 说明：
--   - 只在 exif 中还没有对应 image_id 时插入，保证幂等
--   - 暂时只同步我们目前已经有的字段：camera_make / camera_model / taken_at / gps_lat / gps_lng
INSERT INTO exif (image_id, camera_make, camera_model, taken_at, gps_lat, gps_lng)
SELECT
  i.id          AS image_id,
  i.camera_make AS camera_make,
  i.camera_model AS camera_model,
  i.taken_at    AS taken_at,
  i.gps_lat     AS gps_lat,
  i.gps_lng     AS gps_lng
FROM images i
LEFT JOIN exif e ON e.image_id = i.id
WHERE e.image_id IS NULL
  AND (
       i.camera_make IS NOT NULL
    OR i.camera_model IS NOT NULL
    OR i.taken_at IS NOT NULL
    OR i.gps_lat IS NOT NULL
    OR i.gps_lng IS NOT NULL
  );
