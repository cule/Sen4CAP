#ifndef PHENONDVIHANDLER_HPP
#define PHENONDVIHANDLER_HPP

#include "processorhandler.hpp"

typedef struct {

    NewStepList steps;
    QList<std::reference_wrapper<const TaskToSubmit>> parentsTasksRef;
    // args
    QString metricsParamsImg;
    QString metricsFlagsImg;
    QString tileId;
} PhenoProductFormatterParams;

typedef struct {
    QList<TaskToSubmit> allTasksList;
    NewStepList allStepsList;
    PhenoProductFormatterParams prodFormatParams;
} PhenoGlobalExecutionInfos;

typedef struct {
    QString vegStart;
    QString hstart;
    QString hend;
    QString hstartw;
    QString pstart;
    QString pend;
    QString pstartw;
    QString pendw;
} PracticesTableExtractionParams;

typedef struct {
    QString optthrvegcycle;
    QString ndvidw;
    QString ndviup;
    QString ndvistep;
    QString optthrmin;
    QString cohthrbase;
    QString cohthrhigh;
    QString cohthrabs;
    QString ampthrmin;
    QString efandvithr;
    QString efandviup;
    QString efandvidw;
    QString efacohchange;
    QString efacohvalue;
    QString efandvimin;
    QString efaampthr;
    QString stddevinampthr;
    QString optthrbufden;

    QString catchmain;
    QString catchperiod;
    QString catchperiodstart;
    QString catchcropismain;
    QString catchproportion;

    QString flmarkstartdate;
    QString flmarkstenddate;
} TsaPracticeParams;

typedef struct {
    // Common parameters
    QString country;
    QString year;
    QString fullShapePath;
    QString idsGeomShapePath;

    // Parameters used for practices tables extraction
    QStringList ccAdditionalFiles;
    QStringList flAdditionalFiles;
    QStringList nfcAdditionalFiles;
    QStringList naAdditionalFiles;

    PracticesTableExtractionParams ccPracticeParams;
    PracticesTableExtractionParams flPracticeParams;
    PracticesTableExtractionParams nfcPracticeParams;
    PracticesTableExtractionParams naPracticeParams;

    TsaPracticeParams ccTsaParams;
    TsaPracticeParams flTsaParams;
    TsaPracticeParams nfcTsaParams;
    TsaPracticeParams naTsaParams;

    // parameters used for data extraction step
    int prdsPerGroup;
    QStringList practices;

} AgricPracticesSiteCfg;


class AgricPracticesHandler : public ProcessorHandler
{
private:
    void HandleJobSubmittedImpl(EventProcessingContext &ctx,
                                const JobSubmittedEvent &event) override;
    void HandleTaskFinishedImpl(EventProcessingContext &ctx,
                                const TaskFinishedEvent &event) override;

    void CreateTasks(const AgricPracticesSiteCfg &siteCfg, QList<TaskToSubmit> &outAllTasksList, const QStringList &ndviPrds, const QStringList &ampPrds, const QStringList &cohePrds);
    void CreateSteps(EventProcessingContext &ctx, const JobSubmittedEvent &event, QList<TaskToSubmit> &allTasksList,
                     const AgricPracticesSiteCfg &siteCfg, const QStringList &ndviPrds, const QStringList &ampPrds,
                     const QStringList &cohePrds, NewStepList &steps);
    void WriteExecutionInfosFile(const QString &executionInfosPath,
                                 const QStringList &listProducts);
    QStringList GetProductFormatterArgs(TaskToSubmit &productFormatterTask, EventProcessingContext &ctx, const JobSubmittedEvent &event,
                                        const QStringList &listFiles);

    ProcessorJobDefinitionParams GetProcessingDefinitionImpl(SchedulingContext &ctx, int siteId, int scheduledDate,
                                                const ConfigurationParameterValueMap &requestOverrideCfgValues) override;

private:
    QString GetSiteConfigFilePath(const QString &siteName, const QJsonObject &parameters, std::map<QString, QString> &configParameters);
    AgricPracticesSiteCfg LoadSiteConfigFile(const QString &siteCfgFilePath);

    QStringList ExtractNdviFiles(EventProcessingContext &ctx, const JobSubmittedEvent &event);
    QStringList ExtractAmpFiles(EventProcessingContext &ctx, const JobSubmittedEvent &event);
    QStringList ExtractCoheFiles(EventProcessingContext &ctx, const JobSubmittedEvent &event);
    QStringList GetIdsExtractorArgs(const AgricPracticesSiteCfg &siteCfg, const QString &outFile);
    QStringList GetPracticesExtractionArgs(const AgricPracticesSiteCfg &siteCfg, const QString &outFile, const QString &practice);
    QStringList GetDataExtractionArgs(const AgricPracticesSiteCfg &siteCfg, const QString &filterIdsFile, const QString &prdType, const QString &uidField, const QStringList &inputFiles,
                                      const QString &outDir);
    QStringList GetFilesMergeArgs(const QStringList &listInputPaths, const QString &outFileName);
    QStringList GetTimeSeriesAnalysisArgs(const AgricPracticesSiteCfg &siteCfg, const QString &practice,
                                          const QString &inNdviFile, const QString &inAmpFile, const QString &inCoheFile,
                                          const QString &outDir);
    QString BuildMergeResultFileName(const AgricPracticesSiteCfg &siteCfg, const QString &prdsType);
    QString BuildPracticesTableResultFileName(const AgricPracticesSiteCfg &siteCfg, const QString &practice);

    QStringList CreateStepsForDataExtraction(const AgricPracticesSiteCfg &siteCfg, const QString &prdType,
                                             const QStringList &prds, const QString &idsFileName,
                                             QList<TaskToSubmit> &allTasksList, NewStepList &steps, int &curTaskIdx);

    QString CreateStepsForFilesMerge(const AgricPracticesSiteCfg &siteCfg, const QString &prdType, const QStringList &dataExtrDirs,
                                  NewStepList &steps, QList<TaskToSubmit> &allTasksList, int &curTaskIdx);

    QStringList CreateTimeSeriesAnalysisSteps(const AgricPracticesSiteCfg &siteCfg, const QString &practice,
                                              const QString &ndviMergedFile, const QString &ampMergedFile, const QString &coheMergedFile,
                                              NewStepList &steps, QList<TaskToSubmit> &allTasksList, int &curTaskIdx);

    QStringList GetInputProducts(EventProcessingContext &ctx, const JobSubmittedEvent &event, const ProductType &prdType);
    QString FindNdviProductTiffFile(EventProcessingContext &ctx, const JobSubmittedEvent &event, const QString &path);
};

#endif // PHENONDVIHANDLER_HPP