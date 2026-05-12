-- SQL Server schema for import_premier_mssql.py
-- Assumes schema dbo. Update if needed.

IF OBJECT_ID('dbo.kyc_anomalie', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.kyc_anomalie (
        id INT IDENTITY(1,1) PRIMARY KEY,
        FILIALE NVARCHAR(200) NULL,
        AGENCE NVARCHAR(200) NULL,
        LIB_AGENCE NVARCHAR(50) NULL,
        EXPL NVARCHAR(200) NULL,
        CLIENT NVARCHAR(200) NULL,
        ANOMALIE_AGE NVARCHAR(200) NULL,
        ANOMALIE_DATE_EER NVARCHAR(200) NULL,
        ANOMALIE_CIN NVARCHAR(200) NULL,
        PPE NVARCHAR(200) NULL
    );
END

IF OBJECT_ID('dbo.kyc_daterev', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.kyc_daterev (
        id INT IDENTITY(1,1) PRIMARY KEY,
        FILIALE NVARCHAR(10) NULL,
        AGENCE NVARCHAR(10) NULL,
        LIB_AGENCE NVARCHAR(50) NULL,
        EXPL NVARCHAR(10) NULL,
        CLIENT NVARCHAR(10) NULL,
        DATEREV DATE NULL,
        PPE NVARCHAR(20) NULL,
        RISQUE NVARCHAR(20) NULL
    );
END

IF OBJECT_ID('dbo.kyc_tauxevolution_filiale', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.kyc_tauxevolution_filiale (
        id INT IDENTITY(1,1) PRIMARY KEY,
        filiale NVARCHAR(10) NULL,
        flux_PM FLOAT NULL,
        flux_PP FLOAT NULL,
        stock_PM FLOAT NULL,
        stock_PP FLOAT NULL,
        date DATE NOT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END

-- Optional indexes for import speed and filtering
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = 'IX_kyc_anomalie_filiale' AND object_id = OBJECT_ID('dbo.kyc_anomalie')
)
BEGIN
    CREATE INDEX IX_kyc_anomalie_filiale ON dbo.kyc_anomalie(FILIALE);
END

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = 'IX_kyc_daterev_filiale' AND object_id = OBJECT_ID('dbo.kyc_daterev')
)
BEGIN
    CREATE INDEX IX_kyc_daterev_filiale ON dbo.kyc_daterev(FILIALE);
END

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = 'IX_kyc_tauxevolution_filiale_filiale_date' AND object_id = OBJECT_ID('dbo.kyc_tauxevolution_filiale')
)
BEGIN
    CREATE INDEX IX_kyc_tauxevolution_filiale_filiale_date ON dbo.kyc_tauxevolution_filiale(filiale, date);
END
