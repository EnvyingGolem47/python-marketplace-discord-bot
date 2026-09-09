CREATE TABLE IF NOT EXISTS `district` (
  `district` int NOT NULL,
  `district_id` varchar(45) DEFAULT NULL,
  `district_role_id` varchar(45) DEFAULT NULL,
  `district_comments_id` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`district`)
);

CREATE TABLE IF NOT EXISTS `shop_checks` (
  `shop_check_id` int NOT NULL AUTO_INCREMENT,
  `shop_id` int DEFAULT NULL,
  `checked_by_id` varchar(256) DEFAULT NULL,
  `timestamp` varchar(256) DEFAULT NULL,
  `shop_status` varchar(45) DEFAULT NULL,
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
  `district` int(11) DEFAULT NULL,
  `shop_status` varchar(45) DEFAULT 'Open',
  `mc_owners` TEXT(802) DEFAULT NULL,
  `discord_owners` TEXT(1608) DEFAULT NULL
  PRIMARY KEY (`shop_id`)
);