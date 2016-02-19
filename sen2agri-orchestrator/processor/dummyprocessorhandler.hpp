#pragma once

#include "processorhandler.hpp"

class DummyProcessorHandler : public ProcessorHandler
{
private:
    void HandleProductAvailableImpl(EventProcessingContext &ctx,
                                    const ProductAvailableEvent &event) override;
    void HandleJobSubmittedImpl(EventProcessingContext &ctx,
                                const JobSubmittedEvent &event) override;
    void HandleTaskFinishedImpl(EventProcessingContext &ctx,
                                const TaskFinishedEvent &event) override;

    QString GetProcessingDefinitionJsonImpl(const QJsonObject &procInfoParams, const ProductList &listProducts, bool &bIsValid);
};
