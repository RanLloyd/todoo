-- Pila Senior High School - Attendance Monitoring System
-- MySQL / MariaDB database for XAMPP. Import with phpMyAdmin (Import tab) or: mysql -u root < attendance_monitoring.sql
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;
CREATE DATABASE IF NOT EXISTS `attendance_monitoring` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `attendance_monitoring`;


CREATE TABLE IF NOT EXISTS users(
      id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(100) NOT NULL UNIQUE, password VARCHAR(255) NOT NULL,
      role ENUM('admin','teacher','student') NOT NULL, full_name VARCHAR(200) NOT NULL,
      active TINYINT(1) NOT NULL DEFAULT 1, must_change TINYINT(1) NOT NULL DEFAULT 0, created_at VARCHAR(19)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS students(
      id INT AUTO_INCREMENT PRIMARY KEY, user_id INT UNIQUE, lrn VARCHAR(20) NOT NULL UNIQUE,
      last_name VARCHAR(100) NOT NULL, first_name VARCHAR(100) NOT NULL, middle_name VARCHAR(100),
      sex VARCHAR(1), birthdate VARCHAR(10), age INT, address VARCHAR(500), previous_school VARCHAR(200), grade10_avg DOUBLE,
      contact VARCHAR(100), guardian VARCHAR(200), grade_level VARCHAR(10), strand VARCHAR(50), section VARCHAR(100),
      school_year VARCHAR(20), qr_token VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL UNIQUE,
      CONSTRAINT fk_students_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS terms(
      id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL, start_date VARCHAR(10) NOT NULL, end_date VARCHAR(10) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS attendance(
      id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, day VARCHAR(10) NOT NULL, time_in VARCHAR(8), time_out VARCHAR(8),
      status ENUM('Present','Late','Absent','Excused') NOT NULL DEFAULT 'Present',
      remarks VARCHAR(500), source VARCHAR(20) DEFAULT 'qr',
      UNIQUE KEY uq_att_student_day (student_id, day), KEY idx_att_day (day),
      CONSTRAINT fk_att_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS recitation(
      id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, day VARCHAR(10) NOT NULL, score DOUBLE NOT NULL,
      max_score DOUBLE NOT NULL DEFAULT 10, topic VARCHAR(150),
      UNIQUE KEY uq_rec (student_id, day, topic),
      CONSTRAINT fk_rec_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS assessments(
      id INT AUTO_INCREMENT PRIMARY KEY, kind ENUM('quiz','exam') NOT NULL, title VARCHAR(255) NOT NULL,
      instructions TEXT, term_id INT, time_limit INT DEFAULT 0,
      opens_at VARCHAR(19), due_at VARCHAR(19), published TINYINT(1) NOT NULL DEFAULT 0, show_answers TINYINT(1) NOT NULL DEFAULT 1,
      created_by INT, created_at VARCHAR(19) NOT NULL,
      CONSTRAINT fk_assess_term FOREIGN KEY (term_id) REFERENCES terms(id),
      CONSTRAINT fk_assess_user FOREIGN KEY (created_by) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS questions(
      id INT AUTO_INCREMENT PRIMARY KEY, assessment_id INT NOT NULL, position INT NOT NULL DEFAULT 0,
      qtype ENUM('mcq','tf','text') NOT NULL, prompt TEXT NOT NULL, choices TEXT, answer TEXT NOT NULL, points DOUBLE NOT NULL DEFAULT 1,
      CONSTRAINT fk_q_assess FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS attempts(
      id INT AUTO_INCREMENT PRIMARY KEY, assessment_id INT NOT NULL, student_id INT NOT NULL,
      started_at VARCHAR(19) NOT NULL, submitted_at VARCHAR(19), score DOUBLE, total DOUBLE, answers LONGTEXT,
      UNIQUE KEY uq_attempt (assessment_id, student_id),
      CONSTRAINT fk_att_assess FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
      CONSTRAINT fk_attempt_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS settings(
      setting_key VARCHAR(64) NOT NULL PRIMARY KEY, setting_value VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS login_attempts(
      id INT AUTO_INCREMENT PRIMARY KEY, ident VARCHAR(200) NOT NULL, attempted_at VARCHAR(19) NOT NULL, KEY idx_login_ident (ident)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS activity(
      id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, action VARCHAR(100) NOT NULL, details TEXT, created_at VARCHAR(19) NOT NULL,
      CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- users: 29 rows
INSERT INTO `users` (`id`,`username`,`password`,`role`,`full_name`,`active`,`must_change`,`created_at`) VALUES
(1,'admin','scrypt:32768:8:1$WYyINbn7NqKIZaE1$ecfeb621c056a20462bc10e88eca205747d43b9f4701996f37925be4fdb1653929c620429d79a7b62e68ba8745e2bdb8c24fa86fac7355e2baa122056923ad65','admin','System Administrator',1,1,'2026-10-10T11:02:25'),
(2,'108407140012','scrypt:32768:8:1$sAFv2MWfSDE2gBS2$c61e354d0b5b2ec1c40c057cdd47238b4dcb4e6eb4dc771c3478eebe8a8284f3ee7c95f7ec7bf1b3b25de5199518532bb529145f98cfe0acc8752b0352c2ce03','student','Fitz Emerson S. Castillo',1,1,'2026-10-10T11:02:25'),
(3,'108412140021','scrypt:32768:8:1$7InkllCUyyuNEfGJ$8746b46685ca2eb045f85b65c1582efad4333ef0ec444276564923972d88ce858b8133438f5eaf5a808062370eb26f84a6a21589768e43b598f9134725e19fa6','student','Jerry A. Del Rio',1,1,'2026-10-10T11:02:25'),
(4,'136452150190','scrypt:32768:8:1$dMHeKQRQzhwKnSKg$d4a8ecf94c65b2d6543884494c0b280087510ba73ed4f9970b7e2f03cd8e7fa76dc2f408c44110a44365c1032f29e5062a0fd71af3277d11110aef691d317bea','student','Red E. Embate',1,1,'2026-10-10T11:02:25'),
(5,'108410140078','scrypt:32768:8:1$DDVQjHbJgHCBxPLq$9fff8797e8cf8aa738c47f7f89cc644cc161f7f19b95f5fd16050e66d83d5796a7e30ce8fd12e26802cd1cb8de7b3f9b8f66fbac279ae730b6e7df5a21f49816','student','Alexis B. Javier',1,1,'2026-10-10T11:02:25'),
(6,'108413140069','scrypt:32768:8:1$ipfzaGNqlBILdbCA$56dda589fd69a3ed2bc72bf73e20380601127ce306aa80e70d47c02621fd20e043e03dfc29569a0dbdbfcd9fee999eeb82bc3c4debaa80f23ed7cc31a420cdf8','student','Tyron L. Matienzo',1,1,'2026-10-10T11:02:25'),
(7,'108412140060','scrypt:32768:8:1$8ouowu6bkZZdBlYp$ae0cc5fc7483eef9acf65773395d18323f7fd769b939e2af7e66cc2d4a6554427b6b003db5aef55ff09392be0e4371cb4d8d78d5556ff96083949b694db0f961','student','Prince Lourence P. Nisola',1,1,'2026-10-10T11:02:25'),
(8,'136875150442','scrypt:32768:8:1$RjLxVBThtc9CDSq0$174e42ba48671786956309afee778ac70e336c62da7a4bb1d82a7029a6297b82438e4ebfdd17ab6a28c10942c0943c71e714995335bfcab84982647439fd8246','student','Jhon Michael L. Panimdim',1,1,'2026-10-10T11:02:25'),
(9,'108412140091','scrypt:32768:8:1$AsteXfG6YCwwYTOG$d1cf0a920ee4231b881b63392f9ae1c708cde4b46a0b6d48f13fa945e36945ecbf2fa36ab02496f83c82495f65bd1ed277bf489fc023542630dcb57fc66a7d35','student','Arvin Khen A. Reyes',1,1,'2026-10-10T11:02:26'),
(10,'108405140038','scrypt:32768:8:1$CLLxXgItkvdbhcjL$20e3c562b28efbbd5ab9d39db9d35ea02cc0646dce254ca2e33dd17260ca678c2b41d97862f6ddb052fcd43bfefbbd711f0f3867ed1df2332e23eadf1d14b0f9','student','Vhins Lorcan B. Santiago',1,1,'2026-10-10T11:02:26'),
(11,'108408140020','scrypt:32768:8:1$CJzOgLR8pECnCsoe$2ec2400f06934cf5b65ee2f2f3f06dc8b25913838184e075dc7ba78112169aa6cdfbe71e69b1bb83fab4646e5582048b7280c80fa17777d93db8cabfef41a9ed','student','James Lenard T. Tambalque',1,1,'2026-10-10T11:02:26'),
(12,'108405140039','scrypt:32768:8:1$rOqjXNc2s9F6YHJ3$18fac24d282d26ac4da8033680fa92e0423f17882ba0092db2cf3a738c366b47ed3b2c8d7cefb894b6554b7d3d6a2ed2a329a6b6991e97347fe55770d74bb7b2','student','John Michael M. Teodoro',1,1,'2026-10-10T11:02:26'),
(13,'108408140045','scrypt:32768:8:1$PsgSfkfd90qOhgsv$a30470dea6d9784f3b3247d9aa23f488d041de6020d026e144539da2a68d4cf55911b937ec439853a5f34ad88c75d21db0508181655edd6e761dd42513ea3da8','student','Railey Johanne Abude',1,1,'2026-10-10T11:02:26'),
(14,'108251140217','scrypt:32768:8:1$oGO6aIPYpvhrqNX6$8991a5706c31bcc2380244770e2af746d1065b2d2ce25b88483de317ef018f6dd3ca4f3c4a6624855c0e4192414a0d9df39af27c4050b98eefb194756951783e','student','Zianah Lavigne Ballesteros',1,1,'2026-10-10T11:02:26'),
(15,'108408140051','scrypt:32768:8:1$uhMDSbAbpyYkbQ3O$6851670fc635bc406ed18d5a00fb9012277852b0422580514325de4fd0644978d8eb8327aafc7097aa156cfea9e069105b8a1c3dd74ede46de36212d2b63857f','student','Maria Concepcion A. Capulong',1,1,'2026-10-10T11:02:26'),
(16,'108405140025','scrypt:32768:8:1$ui7fi9C4ln2vHDR8$00c77ed65c778d5c6b6fbe8955c9b68f7bbcfd0bfcebb96f967771da18b79c30b46d73749efa2373675bfa405dc427852caf56d3ee62b436f440c51ed0ae4427','student','Jholianna M. De Leon',1,1,'2026-10-10T11:02:26'),
(17,'108408140057','scrypt:32768:8:1$07fdwl8pQ90jtj3h$36c317ffb4dc741ca5994110490270c44f29409a5e87a3c45bad92cf9ddb18b86d4aa72f046a4623bd8f344c5e1ac4beba25bb96e7a1a51d613f31bf7799fa53','student','Zyann Espinosa',1,1,'2026-10-10T11:02:27'),
(18,'108412140075','scrypt:32768:8:1$SsmPVc5KcYhAEZJ5$5ec888181bbf6af03fd965f6f207e524e985a838ffc2f0e67ac26905f1d4dc74c9794116c9a9dc94b70f1d4c24724dafeb41c587d62a2727c0798c89e9a94ec3','student','Zyan Jenaz D. Larazo',1,1,'2026-10-10T11:02:27'),
(19,'108006130023','scrypt:32768:8:1$bb1nXMICxQB98kox$bbec97ad26b548f867dd12fa5b4ea9c2a87759cf7b08c07a9d8246fb41a3223fa7655301dd817f15a9d9fdbae245e26f9ccdc444295194cfa86ad4dd672b9c15','student','Ma Melissa P. Malate',1,1,'2026-10-10T11:02:27'),
(20,'108408140062','scrypt:32768:8:1$1bdkhVl2Iq7oDCOw$57a6bbae730282222fe230382efb0b08c1d8345d9ac047d3129167710c80367874a9de99e8184664979a6faa4eb19e03a6bfe51809c3943ec5315faa4feb32b4','student','Gweneth Star C. Marasigan',1,1,'2026-10-10T11:02:27'),
(21,'108412140103','scrypt:32768:8:1$GUIEQvIos5t49RL3$a2b4caca4e75324a20e0f320f5421d0449a8c17706aba2fb2fbe633f30c68f784e884b6ebf81489c3d4672372872258395488a2ae23a6d0b8f0a173ca6f11fb5','student','Janna Mitch G. Mendiola',1,1,'2026-10-10T11:02:27'),
(22,'108411140412','scrypt:32768:8:1$7Ml4aOAmPXVUncr4$2f5ec1c2313c8177f1f6ff4e846bff0177beea6db16f840dd70f64b74be770c7039d16251fc75acd5f22c3159fd2253b805247d64d37bb76d7b3b5ebab3c5cbc','student','Rozan G. Pallasigue',1,1,'2026-10-10T11:02:27'),
(23,'108407140055','scrypt:32768:8:1$GiK8b6eOy8BMbVxq$de49b0605bfd0e7864ec62580d9dbffd11c65cdcb7ae1de7be728f50d207b113d9be6a28f4909236c4a7930afc7d9d2c38e02be814b466b9d733176f18b7f2b2','student','Shayne Khimberly O. Pulintan',1,1,'2026-10-10T11:02:27'),
(24,'108408140067','scrypt:32768:8:1$PbXoBNI6hMM0wQu6$6e190ea836531c2063cac85ae22d1dd8a615cd4021bdfa10ffa2e4b1ce8447e83aa977610f71da2c5ac50e86aee58d5c81f1aecd0fb059dc65d7c5e80d53c2a4','student','Marya Lemor A. Rañada',1,1,'2026-10-10T11:02:27'),
(25,'108411140148','scrypt:32768:8:1$MwqFIhnxpkvad74j$c580112c46fce6b9febcc207ed7765c823a137211e1c4211e5e68b5c65f72cfaad93fc3b41acb6b54d1d06dcb6e10e64a657518b2801387e10e505eea174e3c5','student','Jessica B. Rosas',1,1,'2026-10-10T11:02:28'),
(26,'108416140027','scrypt:32768:8:1$6Jw4PAhNyo65dv4L$baa81e7834507d9ec57379bc9aae59fb3ee4b9039320cec4b0457168bfeeda354ee35dbd1d00e02b0716fc2934affcec10dde44aaec081cce9387e5c35e20cb9','student','Erica G. Sultan',1,1,'2026-10-10T11:02:28'),
(27,'108411150132','scrypt:32768:8:1$aVfbYQChJ1geI7xz$b54ccd482379b02810790438b55baa97d6e19c03e4f2fc0a4080446f7499916cfc99819532cb01fed275cefcdecf76d2fbff99736c1f711ebc0f75edd5179f7a','student','Eloisa S. Bandillo',1,1,'2026-10-10T11:02:28'),
(28,'108413120052','scrypt:32768:8:1$I6QkxXYZ6VjtGJ2h$ad021a15e0c7eaed60320ec52c0dd886997356dbca12de6d9f5c66676bdf56c0b765147bf9bfb476b3e126c24434b6cb2a29371d634732f0b9b7028086a2e7f4','student','Merylle Mei G. Samson',1,1,'2026-10-10T11:02:28'),
(29,'ndelrosario','scrypt:32768:8:1$kNRtD35Zw1cnGpbx$3e6e6907cbf269842b3ae988dfafe018c8ab13f373753f07be0cc8173ec4481a50672759d6d1e1ae6107ac4abf82983f503dd1e1cee4bffa51a2fa9d4c7215ab','teacher','Noriel D. Del Rosario',1,1,'2026-10-10T11:02:28');

-- students: 27 rows
INSERT INTO `students` (`id`,`user_id`,`lrn`,`last_name`,`first_name`,`middle_name`,`sex`,`birthdate`,`age`,`address`,`previous_school`,`grade10_avg`,`contact`,`guardian`,`grade_level`,`strand`,`section`,`school_year`,`qr_token`) VALUES
(1,2,'108407140012','Castillo','Fitz Emerson','Sinuhin','M','2009-02-26',16,'Linga, Pila, Laguna','Linga National High School',91.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','gTYXNVUuK69ZgcS2SbGFo9S5'),
(2,3,'108412140021','Del Rio','Jerry','Abayon','M','2009-06-24',16,'Linga, Pila, Laguna','Linga National High School',89.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','2vSZwci-3VaJ5Q1F1QL12Igd'),
(3,4,'136452150190','Embate','Red','Ervas','M','2009-10-07',15,'Linga, Pila, Laguna','Linga National High School',91.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','pl5frow9saAlCTtpW2hYiRBA'),
(4,5,'108410140078','Javier','Alexis','Benitez','M','2009-01-06',16,'Bulilan Sur, Pila, Laguna','Don Manuel Rivera Minhs',80.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','HavaUxK5Yz3-OkA_mD-2HNrr'),
(5,6,'108413140069','Matienzo','Tyron','Lucena','M','2009-10-29',15,'Linga, Pila, Laguna','Linga National High School',93.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','XTr2cA08iCAzd2sAwaMUssu_'),
(6,7,'108412140060','Nisola','Prince Lourence','Palasin','M','2009-08-19',15,'Linga, Pila, Laguna','Linga National High School',89.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','g3D9OLKQO9jGdOqo1B3Nk4PZ'),
(7,8,'136875150442','Panimdim','Jhon Michael','Lopez','M','2009-08-18',15,'Bulilan Sur, Pila, Laguna','Liceo De Pila',85.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','kmFmv1GL9wiEJuwXzPr1rBR-'),
(8,9,'108412140091','Reyes','Arvin Khen','Arnesto','M','2009-07-27',15,'Linga, Pila, Laguna','Linga National High School',87.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','7F1pK1GyqxI_c3PbgBIroxqH'),
(9,10,'108405140038','Santiago','Vhins Lorcan','Bulan','M','2009-08-29',15,'Linga, Pila, Laguna','Linga National High School',97.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','m7obXq3nmGDYH-MWA2iThG4x'),
(10,11,'108408140020','Tambalque','James Lenard','Taguinod','M','2009-04-28',16,'Linga, Pila, Laguna','Linga National High School',90.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','BYkDMMy28JDR8GQBhFAaTmfc'),
(11,12,'108405140039','Teodoro','John Michael','Masuse','M','2009-03-06',16,'Linga, Pila, Laguna','Linga National High School',90.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','MPOj1v3YHg8p2BlcV0oz7a0Z'),
(12,13,'108408140045','Abude','Railey Johanne','','F','2009-09-09',15,'Linga, Pila, Laguna','Linga National High School',92.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','sb5Qm4nA4ComQlmCTC7B9-zZ'),
(13,14,'108251140217','Ballesteros','Zianah Lavigne','','F','2009-07-02',15,'Bulilan Sur, Pila, Laguna','Don Manuel Rivera Minhs',89.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','O8YrpxNphynbqd_LaE_838G_'),
(14,15,'108408140051','Capulong','Maria Concepcion','Añonuevo','F','2008-12-08',16,'Linga, Pila, Laguna','Linga National High School',88.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','gbuqanpFYvmkZTF_G0ospbAs'),
(15,16,'108405140025','De Leon','Jholianna','Mabahin','F','2008-12-19',16,'Linga, Pila, Laguna','Linga National High School',94.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','7HMVR4TBT35W7geE0vF_p7nh'),
(16,17,'108408140057','Espinosa','Zyann','','F','2008-12-21',16,'Linga, Pila, Laguna','Linga National High School',91.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','MJKtFr0HFQEny9z_bRtJwmTJ'),
(17,18,'108412140075','Larazo','Zyan Jenaz','De Guzman','F','2008-12-12',16,'Bulilan Sur, Pila, Laguna','Don Manuel Rivera Minhs',88.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','ojrSv80HT6YWzc4OhiICgaDc'),
(18,19,'108006130023','Malate','Ma Melissa','Pablo','F','2007-11-03',17,'Linga, Pila, Laguna','Linga National High School',91.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','rIK9O463OyHCMiYQEiA4-7SK'),
(19,20,'108408140062','Marasigan','Gweneth Star','Cruz','F','2009-09-28',15,'Linga, Pila, Laguna','Linga National High School',89.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','yEGliHHP2l0prbeL_vZKOOB4'),
(20,21,'108412140103','Mendiola','Janna Mitch','Gomez','F','2009-04-18',16,'Linga, Pila, Laguna','Linga National High School',91.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','b-2urHHWzG61ljsYjmEzY-ri'),
(21,22,'108411140412','Pallasigue','Rozan','Gabo','F','2009-09-27',15,'Bulilan Sur, Pila, Laguna','Don Manuel Rivera Minhs',88.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','PtvFPiQhebBe7aVZXSvXLVYV'),
(22,23,'108407140055','Pulintan','Shayne Khimberly','Ocampo','F','2009-01-02',16,'Linga, Pila, Laguna','Linga National High School',84.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','_5--BPws31D9w5JQvlBKhqqB'),
(23,24,'108408140067','Rañada','Marya Lemor','Arevalo','F','2009-07-15',15,'Linga, Pila, Laguna','Linga National High School',89.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','HYZuvA7pgoA0IwgNGrf8Obbv'),
(24,25,'108411140148','Rosas','Jessica','Balderama','F','2009-02-26',16,'Bulilan Sur, Pila, Laguna','Don Manuel Rivera Minhs',87.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','v9G-6pqiCPoXLZ8YV_s-AYgz'),
(25,26,'108416140027','Sultan','Erica','Gualberto','F','2009-08-29',15,'Bulilan Sur, Pila, Laguna','Don Manuel Rivera Minhs',84.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','2cbP0otgeHRZaUl9MGxsPza9'),
(26,27,'108411150132','Bandillo','Eloisa','Sagayno','F','2009-10-03',15,'Bulilan Sur, Pila, Laguna','Don Manuel Rivera Minhs',87.0,NULL,NULL,'11','HUMSS','Magalang','2025-2026','NmkQ2hAf1JtMiSGPz719jup3'),
(27,28,'108413120052','Samson','Merylle Mei','Gonzales','F','2006-08-13',18,'','',NULL,NULL,NULL,'11','HUMSS','Magalang','2025-2026','THK_Mvnyb9_dwWn_mEPyLqq-');

-- terms: 4 rows
INSERT INTO `terms` (`id`,`name`,`start_date`,`end_date`) VALUES
(1,'1st Quarter','2026-06-08','2026-08-14'),
(2,'2nd Quarter','2026-08-17','2026-10-30'),
(3,'3rd Quarter','2026-11-02','2027-01-22'),
(4,'4th Quarter','2027-01-25','2027-03-31');

-- settings: 11 rows
INSERT INTO `settings` (`setting_key`,`setting_value`) VALUES
('school_name','Pila Senior High School'),
('school_year','2025-2026'),
('late_after','08:00'),
('scan_gap_seconds','60'),
('late_credit','0.75'),
('w_attendance','10'),
('w_recitation','20'),
('w_quiz','30'),
('w_exam','40'),
('passing','75'),
('at_risk_attendance','80');

SET FOREIGN_KEY_CHECKS=1;
