-- === B/S 程序设计 · 图片管理网站 ===
-- 字符集统一为 utf8mb4，避免中文/emoji 乱码
CREATE DATABASE IF NOT EXISTS bs_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bs_db;

-- 用户表（包含 avatar_url）
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username     VARCHAR(50)  NOT NULL UNIQUE,
  email        VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  avatar_url   VARCHAR(255) DEFAULT NULL,                -- 头像 URL，可空，后续资料页可修改
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 图片表（自引用 parent_id；(owner_id, sha256) 去重防止同一用户重复传同图）
CREATE TABLE IF NOT EXISTS images (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_id  INT NOT NULL,
  parent_id INT NULL,
  title       VARCHAR(120) NULL,
  description TEXT NULL,
  path        VARCHAR(255) NOT NULL,                     -- 原图相对路径
  thumb_path  VARCHAR(255) NULL,                         -- 缩略图路径（或后续 thumbs_json）
  sha256      CHAR(64) NOT NULL,                         -- 文件内容哈希（去重关键）
  size        BIGINT DEFAULT 0,
  width       INT NULL,
  height      INT NULL,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_images_owner  FOREIGN KEY (owner_id)  REFERENCES users(id)  ON DELETE CASCADE,
  CONSTRAINT fk_images_parent FOREIGN KEY (parent_id) REFERENCES images(id) ON DELETE SET NULL,
  CONSTRAINT uq_owner_sha256 UNIQUE(owner_id, sha256),   -- 同一 owner 不允许相同内容重复
  INDEX idx_images_owner(owner_id)
) ENGINE=InnoDB;
