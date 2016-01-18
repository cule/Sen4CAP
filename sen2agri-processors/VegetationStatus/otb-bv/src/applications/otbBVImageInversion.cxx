/*=========================================================================
  Program:   otb-bv
  Language:  C++

  Copyright (c) CESBIO. All rights reserved.

  See otb-bv-copyright.txt for details.

  This software is distributed WITHOUT ANY WARRANTY; without even
  the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
  PURPOSE.  See the above copyright notices for more information.

=========================================================================*/

#include "otbWrapperApplication.h"
#include "otbWrapperApplicationFactory.h"
#include "otbWrapperChoiceParameter.h"

#include <fstream>
#include <string>
#include <memory>

#include "otbBVUtil.h"

#include "otbMachineLearningModelFactory.h"
#include "otbNeuralNetworkRegressionMachineLearningModel.h"
#include "otbSVMMachineLearningModel.h"
#include "otbRandomForestsMachineLearningModel.h"
#include "otbMultiLinearRegressionModel.h"
#include "itkListSample.h"
#include "../../../../Composite/Common/GlobalDefs.h"

typedef double PrecisionType;
typedef itk::FixedArray<PrecisionType, 1> OutputSampleType;
typedef itk::VariableLengthVector<PrecisionType> InputSampleType;
typedef itk::Statistics::ListSample<OutputSampleType> ListOutputSampleType;
typedef itk::Statistics::ListSample<InputSampleType> ListInputSampleType;
typedef otb::MachineLearningModel<PrecisionType, PrecisionType> ModelType;
typedef ModelType::Pointer ModelPointerType;
typedef otb::NeuralNetworkRegressionMachineLearningModel<PrecisionType, 
                                                         PrecisionType> 
NeuralNetworkType;
typedef otb::RandomForestsMachineLearningModel<PrecisionType, 
                                               PrecisionType> RFRType;
typedef otb::SVMMachineLearningModel<PrecisionType, PrecisionType> SVRType;
typedef otb::MultiLinearRegressionModel<PrecisionType> MLRType;

namespace otb
{

/** Unary functor image filter which produces a vector image with a
* number of bands different from the input images */
template <class TInputImage, class TOutputImage, 
          class TFunctor>
class ITK_EXPORT UnaryFunctorImageFilterWithNBands : 
    public itk::UnaryFunctorImageFilter< TInputImage, TOutputImage, TFunctor >
{
public:
  typedef UnaryFunctorImageFilterWithNBands Self;
  typedef itk::UnaryFunctorImageFilter< TInputImage, TOutputImage, 
                                        TFunctor > Superclass;
  typedef itk::SmartPointer<Self>       Pointer;
  typedef itk::SmartPointer<const Self> ConstPointer;

  /** Method for creation through the object factory. */
  itkNewMacro(Self);

  /** Macro defining the type*/
  itkTypeMacro(UnaryFunctorImageFilterWithNBands, SuperClass);

  /** Accessors for the number of bands*/
  itkSetMacro(NumberOfOutputBands, unsigned int);
  itkGetConstMacro(NumberOfOutputBands, unsigned int);
  
protected:
  UnaryFunctorImageFilterWithNBands() {}
  virtual ~UnaryFunctorImageFilterWithNBands() {}

  void GenerateOutputInformation()
  {
    Superclass::GenerateOutputInformation();
    this->GetOutput()->SetNumberOfComponentsPerPixel( m_NumberOfOutputBands );
  }
private:
  UnaryFunctorImageFilterWithNBands(const Self &); //purposely not implemented
  void operator =(const Self&); //purposely not implemented

  unsigned int m_NumberOfOutputBands;


};
template <typename InputPixelType, typename OutputPixelType>
class BVEstimationFunctor
{
public:
  BVEstimationFunctor() = default;
  BVEstimationFunctor(ModelType* model,
                      const NormalizationVectorType& normalization) : 
    m_Model{model}, m_Normalization{normalization} {}

  ~BVEstimationFunctor() {};
  
  inline
  OutputPixelType operator ()(const InputPixelType& in_pix)
  {
    bool normalization{m_Normalization!=NormalizationVectorType{}};
    OutputPixelType pix{};
    pix.SetSize(1);
    auto nbInputVariables = in_pix.GetSize();
    InputSampleType inputValue;
    inputValue.Reserve(nbInputVariables);
    int cnt = 0;
    for(size_t var = 0; var < nbInputVariables; ++var)
      {
        if(!IsNoDataValue(in_pix[var])) {
            inputValue[cnt] = in_pix[var];
            if( normalization )
                inputValue[cnt] = normalize(inputValue[cnt], m_Normalization[var]);
            cnt++;
        }
    }
    if(cnt < nbInputVariables) {
        pix[0] = 0;
    } else {
        OutputSampleType outputValue = m_Model->Predict(inputValue);
        pix[0] = outputValue[0];
        if( normalization )
          pix[0] = denormalize(outputValue[0],
                               m_Normalization[nbInputVariables]);
    }
    return pix;
  }

  bool operator !=(const BVEstimationFunctor& other) const
  {
    return (this->m_Model!=other.m_Model ||
            this->m_Normalization!=other.m_Normalization);
  }

  bool operator ==(const BVEstimationFunctor& other) const
  {
    return !(*this!=other);
  }

  bool IsNoDataValue(float fValue)
  {
      return (fValue < NO_DATA_EPSILON);
      //return fabs(fValue - NO_DATA_VALUE) < NO_DATA_EPSILON;
  }


protected:
  ModelPointerType m_Model;
  NormalizationVectorType m_Normalization;

};

namespace Wrapper
{

class BVImageInversion : public Application
{
public:
/** Standard class typedefs. */
  typedef BVImageInversion     Self;
  typedef Application                   Superclass;
  typedef itk::SmartPointer<Self>       Pointer;
  typedef itk::SmartPointer<const Self> ConstPointer;

  
/** Standard macro */
  itkNewMacro(Self);
  itkTypeMacro(BVImageInversion, otb::Application);

  using FunctorType = BVEstimationFunctor<FloatVectorImageType::PixelType, 
                                          FloatVectorImageType::PixelType>;
  using FilterType = UnaryFunctorImageFilterWithNBands<FloatVectorImageType,
                                                       FloatVectorImageType,
                                                       FunctorType>;
  
private:
  void DoInit()
  {
    SetName("BVImageInversion");
    SetDescription("Estimate biophysical variables for every pixel of an image using an inversion of Prospect+Sail.");

    AddParameter(ParameterType_InputImage, "in", "Input Image");
    SetParameterDescription("in","Input image.");

    AddParameter(ParameterType_InputFilename, "model", "File containing the regression model.");
    SetParameterDescription( "model", "File containing the regression model.");
    MandatoryOff("model");

    AddParameter(ParameterType_InputFilename, "modelfile", "File containing paths to the regression model.");
    SetParameterDescription( "modelfile", "File containing paths to the regression model.");
    MandatoryOff("modelfile");

    AddParameter(ParameterType_OutputImage, "out", "Output Image");
    SetParameterDescription("out","Output image.");

    AddRAMParameter();

    AddParameter(ParameterType_InputFilename, "normalization", "Input file containing min and max values per sample component.");
    SetParameterDescription( "normalization", "Input file containing min and max values per sample component. This file can be produced by the invers model learning application. If no file is given as parameter, the variables are not normalized." );
    MandatoryOff("normalization");

  }

  virtual ~BVImageInversion()
  {
  }


  void DoUpdateParameters()
  {
    // Nothing to do here : all parameters are independent
  }

  void DoExecute()
  {
        std::string modelFileName;
        if(!HasValue("model") && !HasValue("modelfile")) {
            itkExceptionMacro("You should specify at least model or the modelslist file name");
        } else {
            if(HasValue("model")) {
                modelFileName = GetParameterString("model");
            }
            // if we have also a file as parameter, get the model path from file
            if(HasValue("modelfile")) {
                std::vector<std::string> modelsFileNames;
                readFileLines(GetParameterString("modelfile"), modelsFileNames);
                if(modelsFileNames.size() > 0)
                    modelFileName = modelsFileNames[0];
            }
        }

        // read output info of the input image
        FloatVectorImageType::Pointer input_image = this->GetParameterImage("in");
        auto nb_bands = input_image->GetNumberOfComponentsPerPixel();
        otbAppLogINFO("Input image has " << nb_bands << " bands."<< std::endl);
        auto nbInputVariables = nb_bands;

        NormalizationVectorType var_minmax{};
        if( HasValue( "normalization" )==true )
        {
            otbAppLogINFO("Variable normalization."<< std::endl);
            var_minmax = read_normalization_file(GetParameterString("normalization"));
            if(var_minmax.size()!=nbInputVariables+1)
                itkGenericExceptionMacro(<< "Normalization file ("<< var_minmax.size()
                                 << " - 1) is not coherent with the number of "
                                 << "input variables ("<< nbInputVariables 
                                 <<").");
            for(size_t var = 0; var < nbInputVariables; ++var)
                otbAppLogINFO("Variable "<< var+1 << " min=" << var_minmax[var].first <<
                      " max=" << var_minmax[var].second <<std::endl);
            otbAppLogINFO("Output min=" << var_minmax[nbInputVariables].first <<
                    " max=" << var_minmax[nbInputVariables].second 
                    << std::endl)
        }

        ModelType* regressor;
        auto nn_regressor = NeuralNetworkType::New();
        auto svr_regressor = SVRType::New();
        auto rfr_regressor = RFRType::New();
        auto mlr_regressor = MLRType::New();
        if(nn_regressor->CanReadFile(modelFileName))
          {
          regressor = dynamic_cast<ModelType*>(nn_regressor.GetPointer());
          otbAppLogINFO("Applying NN regression ..." << std::endl);
          }
        else if(svr_regressor->CanReadFile(modelFileName))
          {
          regressor = dynamic_cast<ModelType*>(svr_regressor.GetPointer());
          otbAppLogINFO("Applying SVR regression ..." << std::endl);
          }
        else if(rfr_regressor->CanReadFile(modelFileName))
          {
          regressor = dynamic_cast<ModelType*>(rfr_regressor.GetPointer());
          otbAppLogINFO("Applying RF regression ..." << std::endl);
          }
        else if(mlr_regressor->CanReadFile(modelFileName))
          {
          regressor = dynamic_cast<ModelType*>(mlr_regressor.GetPointer());
          otbAppLogINFO("Applying MLR regression ..." << std::endl);
          }
        else
          {
          itkGenericExceptionMacro(<< "Model in file " << modelFileName
                                   << " is not valid.\n");
          }
        regressor->Load(modelFileName);

        //instantiate a functor with the regressor and pass it to the
        //unary functor image filter pass also the normalization values
        bv_filter = FilterType::New();
        bv_filter->SetFunctor(FunctorType(regressor,var_minmax));
        bv_filter->SetInput(input_image);
        bv_filter->SetNumberOfOutputBands(1);
        SetParameterOutputImage("out", bv_filter->GetOutput());
  }

  void readFileLines(const std::string &fileName, std::vector<std::string> &outLines) {
      std::ifstream isFile;
      isFile.open(fileName);
      if (!isFile.is_open()) {
          itkExceptionMacro("Can't open file containing model path for reading!");
      }

      // read the file lines
      std::string value;
      while (std::getline(isFile, value)) {
          outLines.push_back(value);
      }

      // close the file
      isFile.close();

  }

  FilterType::Pointer bv_filter;
};

}
}

OTB_APPLICATION_EXPORT(otb::Wrapper::BVImageInversion)
