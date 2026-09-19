CREATE TABLE IF NOT EXISTS `shop_checks` (
  `shop_check_id` int NOT NULL AUTO_INCREMENT,
  `shop_id` int DEFAULT NULL,
  `checked_by_id` varchar(256) DEFAULT NULL,
  `timestamp` varchar(256) DEFAULT NULL,
  `shop_status` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`shop_check_id`)
);
CREATE TABLE IF NOT EXISTS `shops` (
  `shop_id` int NOT NULL,
  `shop_channel_id` varchar(256) DEFAULT NULL,
  `shop_name` varchar(256) DEFAULT NULL,
  `coords` varchar(256) DEFAULT NULL,
  `shop_init` tinyint(4) DEFAULT NULL,
  `large_shop` tinyint(4) DEFAULT NULL,
  `service_shop` tinyint(4) DEFAULT NULL,
  `image` varchar(4096) DEFAULT NULL,
  `district` int(16) DEFAULT NULL,
  `shop_status` varchar(64) DEFAULT 'Open',
  `mc_owners` TEXT(2048) NULL,
  `discord_owners` TEXT(2048) NULL,
  PRIMARY KEY (`shop_id`)
);